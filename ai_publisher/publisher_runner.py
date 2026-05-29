# publisher_runner.py - 发布协调器
#
# 职责：按顺序逐平台发布，更新每个平台的发布结果到任务文件。
# 运行方式：python publisher_runner.py <task_id>
# 由 app.py 通过 subprocess.Popen 启动，不阻塞 Streamlit。

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import task_manager
from config import TaskStatus, PublishStatus, DATA_DIR
from publishers import (
    XiaohongshuPublisher,
    ZhihuPublisher,
    TiebaPublisher,
    WechatPublisher,
)

PUBLISHER_MAP = {
    "xiaohongshu": XiaohongshuPublisher,
    "zhihu":       ZhihuPublisher,
    "tieba":       TiebaPublisher,
    "wechat":      WechatPublisher,
}


def run(task_id: str):
    task = task_manager.load_task(task_id)
    if task is None:
        print(f"[ERROR] 找不到任务 {task_id}")
        return

    task_manager.update_status(task_id, TaskStatus.PUBLISHING)
    platforms = task.get("platforms", [])
    ai_results = task.get("ai_results", {})
    images = task.get("images", [])

    # 将相对路径转为绝对路径
    abs_images = []
    for img in images:
        p = Path(img)
        if not p.is_absolute():
            p = DATA_DIR / img
        if p.exists():
            abs_images.append(str(p))

    for platform in platforms:
        # 检查该平台是否通过审核
        review_status = task.get("review", {}).get(platform, "pending")
        if review_status != "approved":
            print(f"[{platform}] 未通过审核，跳过")
            task_manager.update_publish_result(
                task_id, platform,
                status=PublishStatus.SKIPPED,
                error="未通过审核"
            )
            continue

        content = ai_results.get(platform, {})
        publisher_cls = PUBLISHER_MAP.get(platform)

        if publisher_cls is None:
            print(f"[{platform}] 未找到发布器，跳过")
            task_manager.update_publish_result(
                task_id, platform,
                status=PublishStatus.SKIPPED,
                error="未实现该平台发布器"
            )
            continue

        publisher = publisher_cls()

        # 检查是否已登录（公众号除外，它每次发布时才扫码）
        if platform != "wechat" and not publisher.is_logged_in():
            print(f"[{platform}] 未登录，跳过")
            task_manager.update_publish_result(
                task_id, platform,
                status=PublishStatus.FAILED,
                error="未登录，请先在侧边栏完成登录"
            )
            continue

        print(f"[{platform}] 开始发布...")
        result = publisher._safe_publish(content, abs_images)

        if result["success"]:
            print(f"[{platform}] 发布成功：{result['url']}")
            task_manager.update_publish_result(
                task_id, platform,
                status=PublishStatus.SUCCESS,
                url=result["url"]
            )
        else:
            print(f"[{platform}] 发布失败：{result['error']}")
            task_manager.update_publish_result(
                task_id, platform,
                status=PublishStatus.FAILED,
                error=result["error"]
            )

    print(f"[{task_id}] 所有平台发布完成")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python publisher_runner.py <task_id>")
        sys.exit(1)
    run(sys.argv[1])

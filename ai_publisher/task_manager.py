# task_manager.py - 任务状态机 + 文件持久化
#
# 设计原则：
#   每个任务存为独立的 JSON 文件（data/tasks/{task_id}.json）
#   所有写操作都是原子性的（先写临时文件，再 rename）
#   Streamlit 通过轮询文件来感知状态变更，不共享内存

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import TASKS_DIR, TaskStatus, PublishStatus


# ─────────────────────────────────────────────
# 任务数据结构（dict schema）
# ─────────────────────────────────────────────
#
# {
#   "id": "uuid4",
#   "created_at": "ISO8601",
#   "updated_at": "ISO8601",
#   "status": TaskStatus.*,
#
#   # 用户输入
#   "original_content": "原始文本",
#   "images": ["uploads/xxx.jpg", ...],   # 用户上传的图片路径列表
#   "platforms": ["xiaohongshu", "zhihu", "tieba", "wechat"],
#
#   # AI 分析结果
#   "analysis": {
#     "topic": "核心主题",
#     "keywords": ["关键词1", ...],
#     "emotion": "positive|neutral|negative",
#     "content_type": "教程|测评|观点|资讯|故事",
#     "summary": "50字摘要",
#     "hot_words": ["推荐热词1", ...]
#   },
#
#   # AI 生成的各平台内容
#   "ai_results": {
#     "xiaohongshu": {"title": "", "body": "", "tags": []},
#     "zhihu":       {"title": "", "body": "", "tags": []},
#     "tieba": {
#       "title": "", "body": "", "tags": [],
#       "tieba_candidates": ["候选吧1", "候选吧2", "候选吧3"],  # AI推荐
#       "tieba_selected": None   # 用户审核时选择
#     },
#     "wechat":      {"title": "", "body": ""}
#   },
#
#   # 审核状态（per-platform）
#   "review": {
#     "xiaohongshu": "pending|approved|rejected",
#     ...
#   },
#
#   # 发布结果（per-platform）
#   "publish_results": {
#     "xiaohongshu": {
#       "status": PublishStatus.*,
#       "url": "https://...",
#       "error": "错误信息",
#       "published_at": "ISO8601"
#     },
#     ...
#   },
#
#   # 错误信息（整体任务级别）
#   "error": null
# }


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _task_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.json"


def _atomic_write(path: Path, data: dict):
    """原子写入：先写 .tmp 文件，再 os.replace，防止写一半时崩溃导致文件损坏。os.replace 跨平台原子替换（Windows 也支持）。"""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _lock_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.lock"


@contextmanager
def _task_lock(task_id: str, timeout: float = 5.0):
    """
    任务文件锁，防止多进程（Streamlit + AI 子进程 + 发布子进程）同时修改同一文件。

    使用 O_CREAT | O_EXCL 创建锁文件，该操作在操作系统层面是原子的，
    跨平台兼容（Windows/Linux/macOS）。
    """
    lock = _lock_path(task_id)
    start = time.time()
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.close(fd)
            break
        except FileExistsError:
            if time.time() - start > timeout:
                raise TimeoutError(f"无法获取任务 {task_id} 的文件锁（超时 {timeout}s）")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass  # 另一个进程可能已经释放了


# ─────────────────────────────────────────────
# 公共 API
# ─────────────────────────────────────────────

def create_task(original_content: str, platforms: list[str], images: list[str]) -> dict:
    """
    创建新任务并持久化到文件。
    platforms: 平台 key 列表，如 ["xiaohongshu", "zhihu"]
    images: 已上传到 UPLOADS_DIR 的文件路径列表（相对路径字符串）
    """
    task_id = str(uuid.uuid4())[:8]  # 取前8位，够用且不太长
    now = _now()

    task = {
        "id": task_id,
        "created_at": now,
        "updated_at": now,
        "status": TaskStatus.CREATED,
        "original_content": original_content,
        "images": images,
        "platforms": platforms,
        "analysis": None,
        "ai_results": None,
        "review": {p: "pending" for p in platforms},
        "publish_results": {
            p: {"status": PublishStatus.PENDING, "url": None, "error": None, "published_at": None}
            for p in platforms
        },
        "error": None,
    }

    _atomic_write(_task_path(task_id), task)
    return task


def load_task(task_id: str) -> Optional[dict]:
    """从文件加载单个任务，不存在返回 None"""
    path = _task_path(task_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_task(task: dict):
    """保存任务（更新 updated_at）"""
    task["updated_at"] = _now()
    _atomic_write(_task_path(task["id"]), task)


def load_all_tasks(sort_by_newest: bool = True) -> list[dict]:
    """加载所有任务，默认按创建时间倒序"""
    tasks = []
    for path in TASKS_DIR.glob("*.json"):
        try:
            tasks.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass  # 损坏的文件跳过
    if sort_by_newest:
        tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return tasks


def update_status(task_id: str, status: str, error: str = None):
    """仅更新任务状态（轻量操作，频繁调用用这个）"""
    with _task_lock(task_id):
        task = load_task(task_id)
        if task is None:
            return
        task["status"] = status
        if error is not None:
            task["error"] = error
        save_task(task)


def update_ai_results(task_id: str, analysis: dict, ai_results: dict):
    """AI处理完成后，写入分析结果和各平台内容"""
    with _task_lock(task_id):
        task = load_task(task_id)
        if task is None:
            return
        task["analysis"] = analysis
        task["ai_results"] = ai_results
        task["status"] = TaskStatus.PENDING_REVIEW
        save_task(task)


def approve_platform(task_id: str, platform: str, edited_content: Optional[dict] = None):
    """
    审核通过某个平台。
    edited_content: 用户在审核界面修改后的内容（如果有），会覆盖 AI 生成的内容。
    """
    with _task_lock(task_id):
        task = load_task(task_id)
        if task is None:
            return
        task["review"][platform] = "approved"
        if edited_content and task["ai_results"]:
            task["ai_results"][platform].update(edited_content)
        save_task(task)


def reject_platform(task_id: str, platform: str):
    """审核拒绝（标记为需要重新生成）"""
    with _task_lock(task_id):
        task = load_task(task_id)
        if task is None:
            return
        task["review"][platform] = "rejected"
        save_task(task)


def set_platform_extra_field(task_id: str, platform: str, field_name: str, value):
    """设置某平台 ai_results 中的额外字段（如贴吧吧名选择等）"""
    with _task_lock(task_id):
        task = load_task(task_id)
        if task is None or not task.get("ai_results"):
            return
        if platform in task["ai_results"]:
            task["ai_results"][platform][field_name] = value
        save_task(task)


def update_publish_result(task_id: str, platform: str, status: str,
                           url: str = None, error: str = None):
    """更新某平台的发布结果"""
    with _task_lock(task_id):
        task = load_task(task_id)
        if task is None:
            return
        task["publish_results"][platform] = {
            "status": status,
            "url": url,
            "error": error,
            "published_at": _now() if status == PublishStatus.SUCCESS else None,
        }
        # 检查是否全部完成
        all_results = list(task["publish_results"].values())
        all_done = all(r["status"] in (PublishStatus.SUCCESS, PublishStatus.FAILED, PublishStatus.SKIPPED)
                       for r in all_results)
        if all_done:
            any_success = any(r["status"] == PublishStatus.SUCCESS for r in all_results)
            task["status"] = TaskStatus.COMPLETED if any_success else TaskStatus.FAILED
        save_task(task)


def is_all_approved(task: dict) -> bool:
    """检查所有平台是否都已审核通过"""
    return all(v == "approved" for v in task.get("review", {}).values())


def delete_task(task_id: str):
    """删除任务文件（含锁文件清理）"""
    with _task_lock(task_id):
        path = _task_path(task_id)
        if path.exists():
            path.unlink()

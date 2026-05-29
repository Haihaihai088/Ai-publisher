# publishers/zhihu.py - 知乎发布器
#
# 发布流程：
#   1. 打开 zhuanlan.zhihu.com/write（专栏文章）
#   2. 填写标题
#   3. 填写正文（知乎用的是自定义富文本编辑器）
#   4. 点击"发布"
#
# 注意：知乎富文本编辑器基于 Draft.js，直接 type 即可，不需要特殊处理

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

sys.path.insert(0, str(Path(__file__).parent.parent))
from publishers.base import BasePublisher
import config


class ZhihuPublisher(BasePublisher):
    platform_key  = "zhihu"
    platform_name = "知乎"
    login_url     = "https://www.zhihu.com/signin"

    # ─────────────────────────────────────────
    # 登录：等待跳转离开登录页
    # ─────────────────────────────────────────

    def _wait_for_login(self, page, context) -> bool:
        print("请扫码或输入手机号登录知乎...")
        try:
            # 等待 URL 不再是登录页
            page.wait_for_function(
                "() => !window.location.href.includes('/signin')",
                timeout=120_000
            )
            return True
        except PWTimeout:
            print("等待超时，请重新尝试")
            return False

    # ─────────────────────────────────────────
    # 发布
    # ─────────────────────────────────────────

    def publish(self, content: dict, images: list[str]) -> dict:
        title = content.get("title", "")
        body  = content.get("body", "")
        tags  = content.get("tags", [])

        with sync_playwright() as p:
            context = self._new_context(p)
            page = context.new_page()

            try:
                # 1. 打开写文章页面
                page.goto("https://zhuanlan.zhihu.com/write",
                          wait_until="networkidle", timeout=30_000)

                # 检查是否被重定向到登录页
                if "signin" in page.url:
                    return {"success": False, "url": None, "error": "Cookie 已过期，请重新登录"}

                # 2. 填写标题
                title_input = page.locator('.TitleInput, input[placeholder*="标题"]').first
                title_input.click()
                title_input.fill(title)

                # 3. 填写正文（知乎编辑器是 contenteditable div）
                # 点击编辑区域激活
                editor = page.locator('.DraftEditor-root, .PublishEditor .editorarea').first
                editor.click()

                # 逐段输入
                for line in body.split("\n"):
                    page.keyboard.type(line, delay=10)
                    page.keyboard.press("Enter")

                # 4. 插入图片（如果有）
                if images:
                    try:
                        # 知乎编辑器工具栏的图片按钮
                        img_btn = page.locator('button[data-type="image"], .toolbar-item[title*="图片"]').first
                        img_btn.click(timeout=5_000)
                        page.locator('input[type="file"]').set_input_files(images[:9])  # 最多9张
                        page.wait_for_timeout(3_000)  # 等待上传
                    except PWTimeout:
                        pass  # 图片上传失败不阻断发布

                # 5. 点击发布按钮
                publish_btn = page.locator('button:has-text("发布"), .PublishPanel button').last
                publish_btn.click()

                # 6. 处理发布确认弹窗（知乎有时会弹）
                try:
                    confirm_btn = page.locator('button:has-text("确认发布"), button:has-text("发布文章")').first
                    confirm_btn.click(timeout=5_000)
                except PWTimeout:
                    pass  # 没有弹窗，继续

                # 7. 等待跳转到文章页
                page.wait_for_url("**/zhuanlan.zhihu.com/p/**", timeout=config.PUBLISH_TIMEOUT)
                article_url = page.url

                # 8. 处理话题标签（知乎在发布后可以添加话题，也可在发布前）
                # 简化处理：略过自动添加话题，正文中已包含话题关键词

                self.save_cookies(context.cookies())
                return {"success": True, "url": article_url, "error": None}

            except Exception as e:
                try:
                    page.screenshot(path=str(config.DATA_DIR / "error_zhihu.png"))
                except Exception:
                    pass
                return {"success": False, "url": None, "error": str(e)}
            finally:
                context.browser.close()


if __name__ == "__main__":
    pub = ZhihuPublisher()
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        pub.login_blocking()
    else:
        print("用法：python publishers/zhihu.py login")

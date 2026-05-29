# publishers/xiaohongshu.py - 小红书发布器
#
# 发布流程：
#   1. 打开创作者平台 creator.xiaohongshu.com
#   2. 点击"发布笔记" → 选择"图文笔记"
#   3. 上传图片（至少1张）
#   4. 填写标题（最多20字）
#   5. 填写正文（支持换行和 # 话题标签）
#   6. 点击"发布"

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# 支持直接运行此文件
sys.path.insert(0, str(Path(__file__).parent.parent))
from publishers.base import BasePublisher
import config


class XiaohongshuPublisher(BasePublisher):
    platform_key  = "xiaohongshu"
    platform_name = "小红书"
    login_url     = "https://creator.xiaohongshu.com/login"

    # ─────────────────────────────────────────
    # 登录：等待跳转到首页判断登录成功
    # ─────────────────────────────────────────

    def _wait_for_login(self, page, context) -> bool:
        print("请用小红书 App 扫描页面上的二维码...")
        try:
            page.wait_for_url("**/creator.xiaohongshu.com/**", timeout=120_000)
            # 确保不再是登录页
            page.wait_for_function(
                "() => !window.location.href.includes('/login')",
                timeout=30_000
            )
            return True
        except PWTimeout:
            print("等待超时，请重新尝试登录")
            return False

    # ─────────────────────────────────────────
    # 发布
    # ─────────────────────────────────────────

    def publish(self, content: dict, images: list[str]) -> dict:
        title = content.get("title", "")[:20]      # 小红书标题限制20字
        body  = content.get("body", "")
        tags  = content.get("tags", [])

        # 正文末尾追加话题标签（如果 body 里没有）
        tag_text = " ".join(f"#{t}" for t in tags)
        if tag_text and tag_text not in body:
            body = body.rstrip() + "\n\n" + tag_text

        with sync_playwright() as p:
            context = self._new_context(p)
            page = context.new_page()

            try:
                # 1. 打开发布页
                page.goto("https://creator.xiaohongshu.com/publish/publish",
                          wait_until="networkidle", timeout=30_000)

                # 2. 选择图文笔记（如果有选项卡）
                try:
                    page.locator("text=图文").first.click(timeout=5_000)
                except PWTimeout:
                    pass  # 有些版本没有选项卡，默认就是图文

                # 3. 上传图片
                if images:
                    self._upload_images(
                        page,
                        'input[type="file"][accept*="image"]',
                        images
                    )
                    # 等待图片上传完成（等待缩略图出现）
                    page.wait_for_selector(".upload-item--thumbnail", timeout=30_000)

                # 4. 填写标题
                title_input = page.locator('input[placeholder*="标题"]').first
                title_input.click()
                title_input.fill(title)

                # 5. 填写正文（contenteditable）
                body_editor = page.locator('.ql-editor, [contenteditable="true"]').first
                body_editor.click()
                # 逐行输入，保留换行
                for line in body.split("\n"):
                    page.keyboard.type(line, delay=15)
                    page.keyboard.press("Enter")

                # 6. 点击发布按钮
                publish_btn = page.locator('button:has-text("发布"), button:has-text("发布笔记")').last
                publish_btn.click()

                # 7. 等待发布成功（URL 跳转或成功提示）
                try:
                    page.wait_for_url("**/publish/success**", timeout=config.PUBLISH_TIMEOUT)
                    url = page.url
                except PWTimeout:
                    # 部分情况不跳转，检查提示文字
                    page.wait_for_selector("text=发布成功", timeout=10_000)
                    url = page.url

                # 保存最新 Cookie
                self.save_cookies(context.cookies())
                return {"success": True, "url": url, "error": None}

            except Exception as e:
                # 截图保存，方便排查问题
                screenshot_path = config.DATA_DIR / f"error_xhs_{page.url.split('/')[-1]}.png"
                try:
                    page.screenshot(path=str(screenshot_path))
                except Exception:
                    pass
                return {"success": False, "url": None, "error": str(e)}
            finally:
                context.browser.close()


# ─────────────────────────────────────────────
# 命令行入口：python publishers/xiaohongshu.py login
# ─────────────────────────────────────────────
if __name__ == "__main__":
    pub = XiaohongshuPublisher()
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        pub.login_blocking()
    else:
        print("用法：python publishers/xiaohongshu.py login")

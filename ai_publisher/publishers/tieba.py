# publishers/tieba.py - 贴吧发布器
#
# 发布流程：
#   1. 打开目标贴吧页面 tieba.baidu.com/f?kw={吧名}
#   2. 点击"发帖"按钮
#   3. 填写标题
#   4. 填写正文
#   5. 上传图片（可选）
#   6. 点击"发布"

import sys
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

sys.path.insert(0, str(Path(__file__).parent.parent))
from publishers.base import BasePublisher
import config


class TiebaPublisher(BasePublisher):
    platform_key      = "tieba"
    platform_name     = "贴吧"
    login_url         = "https://tieba.baidu.com/"
    icon              = "🐧"
    has_bar_selection = True

    # ─────────────────────────────────────────
    # 登录：百度账号扫码
    # ─────────────────────────────────────────

    def _wait_for_login(self, page, context) -> bool:
        """百度贴吧：点登录按钮 → 扫码"""
        try:
            # 点击右上角登录按钮
            login_btn = page.locator('a:has-text("登录"), .u_login').first
            login_btn.click(timeout=10_000)
        except PWTimeout:
            pass

        print("请扫码或输入账号登录百度贴吧...")
        try:
            # 等待登录成功（页面出现用户头像或昵称）
            page.wait_for_selector('.u_name, .user-name, .userName', timeout=120_000)
            return True
        except PWTimeout:
            print("等待超时，请重新尝试")
            return False

    # ─────────────────────────────────────────
    # 发布
    # ─────────────────────────────────────────

    def publish(self, content: dict, images: list[str]) -> dict:
        title         = content.get("title", "")
        body          = content.get("body", "")
        tieba_name    = content.get("tieba_selected", "")   # 用户审核时选择的吧名

        if not tieba_name:
            return {"success": False, "url": None,
                    "error": "未选择目标贴吧，请在审核队列中选择吧名"}

        with sync_playwright() as p:
            context = self._new_context(p)
            page = context.new_page()

            try:
                # 1. 打开目标贴吧
                bar_url = f"https://tieba.baidu.com/f?kw={quote(tieba_name)}&ie=utf-8"
                page.goto(bar_url, wait_until="domcontentloaded", timeout=30_000)

                # 检查是否需要登录
                if "passport.baidu.com" in page.url:
                    return {"success": False, "url": None, "error": "Cookie 已过期，请重新登录"}

                # 2. 点击"发帖"按钮
                post_btn = page.locator(
                    'a:has-text("发帖"), .core_title_btn_wrapper a, #thread_submit'
                ).first
                post_btn.click(timeout=10_000)

                # 等待发帖页面加载
                page.wait_for_load_state("networkidle", timeout=15_000)

                # 3. 填写标题
                title_input = page.locator(
                    'input[name="title"], input[placeholder*="标题"], #title'
                ).first
                title_input.click()
                title_input.fill(title)

                # 4. 填写正文
                # 贴吧编辑器有两种：老版普通 textarea 和新版富文本
                try:
                    # 尝试新版富文本编辑器
                    editor = page.locator('.ProseMirror, [contenteditable="true"]').first
                    editor.wait_for(timeout=5_000)
                    editor.click()
                    for line in body.split("\n"):
                        page.keyboard.type(line, delay=10)
                        page.keyboard.press("Enter")
                except PWTimeout:
                    # 回退到老版 textarea
                    textarea = page.locator('textarea[name="content"], #content').first
                    textarea.fill(body)

                # 5. 上传图片（可选）
                if images:
                    try:
                        img_btn = page.locator(
                            'button[title*="图片"], .insert-img, .pic-button'
                        ).first
                        img_btn.click(timeout=5_000)
                        page.locator('input[type="file"]').set_input_files(images[:9])
                        page.wait_for_timeout(3_000)
                    except PWTimeout:
                        pass  # 图片上传失败不阻断

                # 6. 提交发帖
                submit_btn = page.locator(
                    'button[type="submit"], input[type="submit"], button:has-text("发布"), #submit'
                ).last
                submit_btn.click()

                # 7. 等待发帖成功（跳转到帖子页或出现成功提示）
                try:
                    page.wait_for_url("**/tieba.baidu.com/p/**", timeout=config.PUBLISH_TIMEOUT)
                    post_url = page.url
                except PWTimeout:
                    # 部分情况不跳转，尝试找成功提示
                    page.wait_for_selector("text=发布成功, text=发帖成功", timeout=10_000)
                    post_url = page.url

                self.save_cookies(context.cookies())
                return {"success": True, "url": post_url, "error": None}

            except Exception as e:
                try:
                    page.screenshot(path=str(config.DATA_DIR / "error_tieba.png"))
                except Exception:
                    pass
                return {"success": False, "url": None, "error": str(e)}
            finally:
                context.browser.close()


if __name__ == "__main__":
    pub = TiebaPublisher()
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        pub.login_blocking()
    else:
        print("用法：python publishers/tieba.py login")

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
from patchright.sync_api import sync_playwright, TimeoutError as PWTimeout

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

                if "passport.baidu.com" in page.url:
                    return {"success": False, "url": None, "error": "Cookie 已过期，请重新登录"}

                # 2. 点击"发帖"按钮
                post_btn = page.locator(
                    'a:has-text("发帖"), .core_title_btn_wrapper a, '
                    '.tbui_aside_float_bar .tbui_aside_float_bar_new_post'
                ).first
                post_btn.click(timeout=10_000)
                page.wait_for_timeout(2000)

                # 3. 填写标题（贴吧新版编辑器标题在 modal 中）
                title_input = page.locator(
                    'input[name="title"], input[placeholder*="标题"], '
                    'input[placeholder*="输入标题"], #title, '
                    '.editor-title-input'
                ).first
                title_input.wait_for(state="visible", timeout=10_000)
                title_input.click()
                page.wait_for_timeout(300)
                title_input.fill(title)

                # 4. 填写正文 — insert_text 一次性粘贴
                editor = page.locator(
                    '.ProseMirror, [contenteditable="true"], '
                    'textarea[name="content"], #content, .editor-content'
                ).first
                editor.wait_for(state="visible", timeout=10_000)
                editor.click()
                page.wait_for_timeout(300)

                # 判断编辑器类型
                tag_name = editor.evaluate("el => el.tagName")
                if tag_name == "TEXTAREA":
                    editor.fill(body)
                else:
                    page.keyboard.insert_text(body)

                # 5. 上传图片 — 文件选择器模式（参照快手 social-auto-upload）
                if images:
                    try:
                        img_btn = page.locator(
                            '[title*="图片"], [aria-label*="图片"], '
                            '.tbui_icon_picture, .icon-picture, '
                            'a:has-text("图片"), .insert-img'
                        ).first
                        with page.expect_file_chooser() as fc_info:
                            img_btn.click(timeout=5_000)
                        file_chooser = fc_info.value
                        file_chooser.set_files(images[:9])
                        page.wait_for_timeout(5_000)
                    except Exception:
                        # fallback: 直接找 file input
                        try:
                            file_input = page.locator('input[type="file"]').first
                            file_input.wait_for(state="attached", timeout=5_000)
                            file_input.set_input_files(images[:9])
                            page.wait_for_timeout(5_000)
                        except Exception:
                            pass

                # 6. 提交 — 重试循环模式
                for _ in range(10):
                    try:
                        submit_btn = page.locator(
                            'button[type="submit"], input[type="submit"], '
                            'button:has-text("发布"), button:has-text("发表"), #submit'
                        ).last
                        submit_btn.click(timeout=3000)
                        page.wait_for_url("**/tieba.baidu.com/p/**", timeout=5000)
                        break
                    except Exception:
                        page.wait_for_timeout(2000)

                # 7. 等待发帖成功
                post_url = page.url
                try:
                    page.wait_for_url("**/tieba.baidu.com/p/**", timeout=config.PUBLISH_TIMEOUT)
                    post_url = page.url
                except PWTimeout:
                    try:
                        page.wait_for_selector("text=发布成功, text=发帖成功", timeout=10_000)
                    except Exception:
                        pass

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


# ─────────────────────────────────────────────
# 注册到 PlatformRegistry
# ─────────────────────────────────────────────

from platform_registry import PlatformRegistry, PlatformDescriptor

PlatformRegistry.register(PlatformDescriptor(
    key="tieba",
    name="贴吧",
    icon="🐧",
    publisher_class=TiebaPublisher,
    login_url="https://tieba.baidu.com/",
    has_bar_selection=True,
    ai_spec="""
贴吧规范：
- title：口语化帖子标题，可带疑问或感叹，50字以内
- body：300-600字，楼主视角，接地气，段落短，开头可用"说真的""来跟大家聊聊"等自然引入，结尾引导其他人跟帖讨论（如"你们怎么看？""有没有同款？"）
- tags：2-3个相关词（不带#号，用于搜索）""",
    output_schema='"tieba": {"title": "...", "body": "...", "tags": [...]}',
))

if __name__ == "__main__":
    pub = TiebaPublisher()
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        pub.login_blocking()
    else:
        print("用法：python publishers/tieba.py login")

# publishers/wechat.py - 公众号发布器
#
# 特殊说明：
#   mp.weixin.qq.com 每次访问都需要微信扫码，Cookie 无法持久化。
#   因此：
#     - is_logged_in() 始终返回 True（账号"存在"，每次发布前扫码）
#     - 发布时打开浏览器展示二维码，等用户扫码后继续
#     - 审核队列里已提前告知用户
#
# 发布流程：
#   1. 打开 mp.weixin.qq.com
#   2. 等待用户扫码登录
#   3. 点击"新建图文" / "写文章"
#   4. 填写标题和正文
#   5. 上传封面图（第一张图片）
#   6. 点击"发表"

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

sys.path.insert(0, str(Path(__file__).parent.parent))
from publishers.base import BasePublisher
import config


class WechatPublisher(BasePublisher):
    platform_key  = "wechat"
    platform_name = "公众号"
    login_url     = "https://mp.weixin.qq.com/"

    # 公众号每次都需要扫码，不依赖 Cookie
    def is_logged_in(self) -> bool:
        """公众号视为"已配置"（每次发布时扫码）"""
        # 创建一个标志文件表示用户已知晓并配置了公众号
        return config.get_cookie_path("wechat_configured").exists()

    def mark_configured(self):
        """用户首次确认使用公众号后，创建标志文件"""
        path = config.get_cookie_path("wechat_configured")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("configured")

    # 公众号不用常规登录流程，改为首次"配置确认"
    def login_blocking(self):
        """打开公众号页面让用户确认账号可用"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=300)
            context = browser.new_context(locale="zh-CN")
            page = context.new_page()
            page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded")
            print("请用微信扫码登录公众号后台，验证账号可用...")
            input("确认可以正常登录后按 Enter...")
            self.mark_configured()
            print("公众号已配置完成")
            browser.close()

    # ─────────────────────────────────────────
    # 发布（每次都需要扫码）
    # ─────────────────────────────────────────

    def publish(self, content: dict, images: list[str]) -> dict:
        title = content.get("title", "")
        body  = content.get("body", "")

        with sync_playwright() as p:
            # 公众号不注入 Cookie，每次全新登录
            browser = p.chromium.launch(
                headless=False,
                slow_mo=config.BROWSER_SLOW_MO,
                args=["--no-sandbox"]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN"
            )
            page = context.new_page()

            try:
                # 1. 打开公众号后台（会显示扫码页）
                page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded")

                # 2. 等待扫码登录（等待进入后台首页）
                print("[公众号] 请用微信扫码登录...")
                try:
                    page.wait_for_selector(
                        '#app, .main-nav, .weui-desktop-nav',
                        timeout=120_000
                    )
                except PWTimeout:
                    return {"success": False, "url": None, "error": "扫码超时，请重试"}

                # 3. 点击"写文章" / "新建图文消息"
                try:
                    write_btn = page.locator(
                        'a:has-text("写文章"), a:has-text("新建图文消息"), '
                        'a:has-text("写文章"), .new-creation__menu-item'
                    ).first
                    write_btn.click(timeout=10_000)
                except PWTimeout:
                    # 备选：通过菜单进入
                    page.goto("https://mp.weixin.qq.com/cgi-bin/appmsgpublish?action=edit",
                              wait_until="domcontentloaded")

                # 等待编辑器加载
                page.wait_for_load_state("networkidle", timeout=20_000)

                # 4. 填写标题
                title_input = page.locator(
                    '#title, input[placeholder*="标题"], .title-input'
                ).first
                title_input.click()
                title_input.fill(title)

                # 5. 填写正文（公众号编辑器是 iframe 内的富文本）
                # 先尝试找 iframe
                try:
                    frame = page.frame_locator('#ueditor_0, iframe[id*="editor"]').first
                    body_el = frame.locator('body, #ueditorBody')
                    body_el.click()
                    for line in body.split("\n"):
                        page.keyboard.type(line, delay=10)
                        page.keyboard.press("Enter")
                except Exception:
                    # 备选：直接找 contenteditable
                    editor = page.locator('[contenteditable="true"]').nth(1)
                    editor.click()
                    for line in body.split("\n"):
                        page.keyboard.type(line, delay=10)
                        page.keyboard.press("Enter")

                # 6. 上传封面图（使用第一张图片）
                if images:
                    try:
                        cover_btn = page.locator(
                            'text=封面, .cover-upload, button:has-text("上传封面")'
                        ).first
                        cover_btn.click(timeout=5_000)
                        page.locator('input[type="file"]').first.set_input_files(images[0])
                        page.wait_for_timeout(3_000)
                        # 确认裁剪（如有弹窗）
                        try:
                            page.locator('button:has-text("确定"), button:has-text("完成")').first.click(timeout=3_000)
                        except PWTimeout:
                            pass
                    except PWTimeout:
                        pass  # 封面上传失败不阻断

                # 7. 点击"发表"
                publish_btn = page.locator(
                    'button:has-text("发表"), a:has-text("发表"), '
                    '.publish-btn, #js_submit'
                ).last
                publish_btn.click()

                # 8. 处理发表确认弹窗
                try:
                    confirm = page.locator(
                        'button:has-text("确定发表"), button:has-text("群发")'
                    ).first
                    confirm.click(timeout=8_000)
                except PWTimeout:
                    pass

                # 9. 等待发表成功
                try:
                    page.wait_for_selector(
                        "text=发表成功, text=群发成功, .success-tips",
                        timeout=config.PUBLISH_TIMEOUT
                    )
                except PWTimeout:
                    # 有些版本是跳转
                    pass

                final_url = page.url
                return {"success": True, "url": final_url, "error": None}

            except Exception as e:
                try:
                    page.screenshot(path=str(config.DATA_DIR / "error_wechat.png"))
                except Exception:
                    pass
                return {"success": False, "url": None, "error": str(e)}
            finally:
                browser.close()


if __name__ == "__main__":
    pub = WechatPublisher()
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        pub.login_blocking()
    else:
        print("用法：python publishers/wechat.py login")

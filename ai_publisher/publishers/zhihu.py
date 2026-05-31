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
from patchright.sync_api import sync_playwright, TimeoutError as PWTimeout

sys.path.insert(0, str(Path(__file__).parent.parent))
from publishers.base import BasePublisher
import config


class ZhihuPublisher(BasePublisher):
    platform_key  = "zhihu"
    platform_name = "知乎"
    login_url     = "https://www.zhihu.com/signin"
    icon          = "💡"

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

                # 2. 填写标题 — 只匹配标题相关输入框
                title_input = page.locator(
                    # 知乎专栏标题输入框
                    'textarea[placeholder*="输入标题"], '
                    'input[placeholder*="文章标题"], '
                    'textarea[placeholder*="标题"], '
                    '.Write-titleInput input, '
                    '.TitleInput input, '
                    'input[data-testid*="title"], '
                    '[class*="WriteTitle"] input'
                ).first
                title_input.wait_for(state="visible", timeout=15_000)
                title_input.click()
                page.wait_for_timeout(300)
                title_input.fill(title)

                # 3. 填写正文 — insert_text 一次性粘贴
                # 知乎编辑器：先点击编辑区域激活
                editor = page.locator(
                    '[contenteditable="true"], '
                    '.DraftEditor-root, .public-DraftEditor-content, '
                    '[role="textbox"], [class*="editor"], '
                    '[class*="Editor"]'
                ).first
                editor.wait_for(state="visible", timeout=10_000)
                editor.click()
                page.wait_for_timeout(500)

                # 一次性粘贴全文（insert_text 比逐行 type 快几十倍）
                page.keyboard.insert_text(body)

                # 4. 插入图片 — 尝试找图片上传入口
                if images:
                    try:
                        # 策略A: 点击工具栏图片按钮
                        img_btn = page.locator(
                            '[aria-label*="图片"], '
                            'button[data-tooltip*="图片"], '
                            '.toolbar-item:has-text("图片"), '
                            'svg[class*="image"], '
                            'button:has-text("图片")'
                        ).first
                        img_btn.click(timeout=3_000)
                        page.wait_for_timeout(800)
                    except Exception:
                        pass

                    try:
                        # 策略B: 直接找 file input（可能始终在DOM中）
                        file_input = page.locator('input[type="file"]').first
                        file_input.wait_for(state="attached", timeout=5_000)
                        file_input.set_input_files(images[:9])
                        page.wait_for_timeout(5_000)
                    except Exception:
                        pass  # 图片上传失败不阻断发布

                # 5. 点击发布按钮
                publish_btn = page.locator(
                    'button:has-text("发布"), .PublishPanel button, '
                    '[class*="publish"] button, [class*="submit"] button'
                ).last
                publish_btn.wait_for(state="visible", timeout=10_000)
                publish_btn.click()

                # 6. 处理发布确认弹窗
                try:
                    confirm_btn = page.locator(
                        'button:has-text("确认发布"), button:has-text("发布文章"), '
                        'button:has-text("确定")'
                    ).first
                    confirm_btn.click(timeout=5_000)
                except PWTimeout:
                    pass

                # 7. 等待跳转到文章页
                page.wait_for_url("**/zhuanlan.zhihu.com/p/**", timeout=config.PUBLISH_TIMEOUT)
                article_url = page.url

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


# ─────────────────────────────────────────────
# 注册到 PlatformRegistry
# ─────────────────────────────────────────────

from platform_registry import PlatformRegistry, PlatformDescriptor

PlatformRegistry.register(PlatformDescriptor(
    key="zhihu",
    name="知乎",
    icon="💡",
    publisher_class=ZhihuPublisher,
    login_url="https://www.zhihu.com/signin",
    ai_spec="""
知乎规范：
- title：问题式或观点式，引发思考，40字以内，不用感叹号
- body：800-1500字，逻辑严密，可用"**小标题**"分段，语言专业但口语化，可引用数据或案例，结尾给出明确结论，不要"我认为""笔者认为"
- tags：2-3个知乎话题标签（不带#号）""",
    output_schema='"zhihu": {"title": "...", "body": "...", "tags": [...]}',
))

if __name__ == "__main__":
    pub = ZhihuPublisher()
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        pub.login_blocking()
    else:
        print("用法：python publishers/zhihu.py login")

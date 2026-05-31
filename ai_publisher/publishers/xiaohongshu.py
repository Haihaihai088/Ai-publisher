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
from patchright.sync_api import sync_playwright, TimeoutError as PWTimeout

# 支持直接运行此文件
sys.path.insert(0, str(Path(__file__).parent.parent))
from publishers.base import BasePublisher
import config


class XiaohongshuPublisher(BasePublisher):
    platform_key  = "xiaohongshu"
    platform_name = "小红书"
    login_url     = "https://creator.xiaohongshu.com/login"
    icon          = "📕"

    # ─────────────────────────────────────────
    # 登录：等待跳转到首页判断登录成功
    # ─────────────────────────────────────────

    def _wait_for_login(self, page, context) -> bool:
        print("请用小红书 App 扫描页面上的二维码...")
        try:
            # 等待 URL 离开登录页（不要用 wait_for_url **/creator.xiaohongshu.com/**
            # 因为登录页本身就在该域名下，会立即匹配）
            page.wait_for_function(
                "() => !window.location.href.includes('/login')",
                timeout=120_000
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

        MAX_BODY = 1000
        if len(body) > MAX_BODY:
            body = body[:MAX_BODY - 3] + "..."

        with sync_playwright() as p:
            context = self._new_context(p)
            page = context.new_page()

            try:
                # 1. 打开图文发布页
                page.goto(
                    "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=image",
                    wait_until="networkidle", timeout=30_000
                )

                # 2. 上传图片（参照 social-auto-upload 模式）
                if images:
                    upload_input = page.locator('input[type="file"][accept*="image"]').first
                    if not upload_input.count():
                        upload_input = page.locator(
                            "div[class^='upload-content'] input[class='upload-input']"
                        ).first
                    upload_input.wait_for(state="attached", timeout=30_000)
                    upload_input.set_input_files(images)
                    # 等待标题输入框出现 = 图片上传完成
                    page.locator('input[placeholder*="填写标题"]').first.wait_for(
                        state="visible", timeout=60_000
                    )

                # 3. 填写标题（fill 一步到位）
                title_input = page.locator('input[placeholder*="填写标题"]').first
                title_input.wait_for(state="visible", timeout=10_000)
                title_input.fill(title)

                # 4. 填写正文（完全对齐 social-auto-upload fill_desc）
                desc_editor = page.locator('p[data-placeholder*="输入正文描述"]').first
                desc_editor.wait_for(state="visible", timeout=10_000)
                desc_editor.click()
                page.keyboard.press("Backspace")
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                page.keyboard.type(body)
                page.keyboard.press("Enter")  # ← 关键：Enter 收尾才能激活发布按钮

                # 5. 追加话题标签（参照 social-auto-upload fill_tags 模式）
                for tag in tags:
                    page.keyboard.type("#" + tag, delay=30)
                    try:
                        topic_container = page.locator('#creator-editor-topic-container').first
                        topic_container.wait_for(state="visible", timeout=3000)
                        first_item = page.locator('#creator-editor-topic-container .item').first
                        first_item.click()
                    except Exception:
                        pass

                # 6. 发布 — 参照 social-auto-upload 重试循环模式
                url = page.url
                for _ in range(30):  # 最多重试 30 次
                    try:
                        page.locator('button:has-text("发布")').click()
                        page.wait_for_url("**/publish/success**", timeout=3000)
                        url = page.url
                        break
                    except Exception:
                        page.wait_for_timeout(1000)

                self.save_cookies(context.cookies())
                return {"success": True, "url": url, "error": None}

            except Exception as e:
                try:
                    page.screenshot(path=str(config.DATA_DIR / "error_xhs_publish.png"))
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
    key="xiaohongshu",
    name="小红书",
    icon="📕",
    publisher_class=XiaohongshuPublisher,
    login_url="https://creator.xiaohongshu.com/login",
    ai_spec="""
小红书规范：
- title：20字以内，带1-2个 Emoji，制造好奇心或情绪共鸣，不能太广告
- body：300-500字，段落极短（每段1-3行），段落间空行，穿插 Emoji，结尾自然带入2-4个#话题标签，像真人在分享日常或经验
- tags：3-5个精准标签（不带#号）""",
    output_schema='"xiaohongshu": {"title": "...", "body": "...", "tags": [...]}',
))

# ─────────────────────────────────────────────
# 命令行入口：python publishers/xiaohongshu.py login
# ─────────────────────────────────────────────
if __name__ == "__main__":
    pub = XiaohongshuPublisher()
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        pub.login_blocking()
    else:
        print("用法：python publishers/xiaohongshu.py login")

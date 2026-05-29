# publishers/mock.py - 模拟发布器
#
# 不打开真实浏览器，不依赖任何平台账号。
# 用于测试完整发布流程或演示，无需安装 Playwright 浏览器。
# 启用方式：.env 中设置 SIMULATED_MODE=true 或在 UI 侧边栏中打开"模拟发布模式"。

import time
import random
from pathlib import Path

from publishers.base import BasePublisher
from platform_registry import PlatformRegistry, PlatformDescriptor


class MockPublisher(BasePublisher):
    platform_key  = "mock"
    platform_name = "模拟发布"
    login_url     = ""
    icon          = "🧪"

    skip_login_check = True
    has_tags         = True

    def is_logged_in(self) -> bool:
        return True

    def publish(self, content: dict, images: list[str]) -> dict:
        # 模拟发布流程（不涉及任何浏览器操作）
        delay = random.uniform(1.0, 3.0)
        time.sleep(delay)

        mock_id = random.randint(1000, 99999)
        return {
            "success": True,
            "url": f"https://mock.example.com/p/{mock_id}",
            "error": None,
        }

    # 模拟发布不需要登录
    def start_login_subprocess(self):
        pass


# 自注册到 PlatformRegistry
PlatformRegistry.register(PlatformDescriptor(
    key="mock",
    name="模拟发布",
    icon="🧪",
    publisher_class=MockPublisher,
    login_url="",
    skip_login_check=True,
    has_tags=True,
    ai_spec="""
模拟发布规范：
- title：20字以内，一个示例标题
- body：200-400字，模拟正文内容
- tags：2-3个模拟标签
""",
    output_schema='"mock": {"title": "...", "body": "...", "tags": [...]}',
))

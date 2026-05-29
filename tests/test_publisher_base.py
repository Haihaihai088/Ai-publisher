# tests/test_publisher_base.py — 发布器基类 Cookie 管理测试
import os
import sys
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "ai_publisher"))

# Mock dotenv 和 playwright 避免需要安装依赖（必须在 import 前注入 sys.modules）
sys.modules["dotenv"] = MagicMock()
_mock_pw = MagicMock()
sys.modules["playwright"] = _mock_pw
sys.modules["playwright.sync_api"] = _mock_pw

from publishers.base import BasePublisher


class TestBasePublisher(unittest.TestCase):
    """测试 BasePublisher 的 Cookie 读写和属性，不涉及 Playwright"""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.cookies_dir = Path(cls.tmpdir.name) / "cookies"
        cls.cookies_dir.mkdir(parents=True, exist_ok=True)
        cls.BasePublisher = BasePublisher

    def setUp(self):
        # 每个测试前清理临时目录中的残留文件
        for f in self.cookies_dir.glob("*"):
            f.unlink()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _make_publisher(self):
        """创建一个可用测试的具体子类实例"""
        class TestPublisher(self.BasePublisher):
            platform_key = "test_platform"
            platform_name = "测试平台"
            login_url = "https://example.com/login"
            def publish(self, content, images):
                return {"success": True, "url": None, "error": None}

        pub = TestPublisher()
        # 覆盖 cookie_path 指向临时目录
        pub.cookie_path = self.cookies_dir / "test_platform.json"
        return pub

    def test_is_logged_in_false_initially(self):
        pub = self._make_publisher()
        self.assertFalse(pub.is_logged_in())

    def test_save_and_load_cookies(self):
        pub = self._make_publisher()
        test_cookies = [
            {"name": "session", "value": "abc123", "domain": ".example.com"}
        ]
        pub.save_cookies(test_cookies)
        self.assertTrue(pub.is_logged_in())
        loaded = pub.load_cookies()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["name"], "session")

    def test_clear_cookies(self):
        pub = self._make_publisher()
        pub.save_cookies([{"name": "x", "value": "y"}])
        self.assertTrue(pub.is_logged_in())
        pub.clear_cookies()
        self.assertFalse(pub.is_logged_in())

    def test_clear_nonexistent_cookies_no_error(self):
        pub = self._make_publisher()
        pub.clear_cookies()
        self.assertFalse(pub.is_logged_in())

    def test_load_nonexistent_cookies_returns_none(self):
        pub = self._make_publisher()
        result = pub.load_cookies()
        self.assertIsNone(result)

    def test_save_preserves_json_structure(self):
        pub = self._make_publisher()
        cookies = [
            {"name": "a", "value": "1", "domain": "x.com"},
            {"name": "b", "value": "2", "domain": "y.com", "httpOnly": True}
        ]
        pub.save_cookies(cookies)
        raw = pub.cookie_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[1]["httpOnly"], True)

    def test_platform_key_and_name_required(self):
        pub = self._make_publisher()
        self.assertEqual(pub.platform_key, "test_platform")
        self.assertEqual(pub.platform_name, "\u6d4b\u8bd5\u5e73\u53f0")

    def test_cookies_unicode(self):
        pub = self._make_publisher()
        cookies = [{"name": "\u7528\u6237", "value": "\u4e2d\u6587\u503c"}]
        pub.save_cookies(cookies)
        loaded = pub.load_cookies()
        self.assertEqual(loaded[0]["value"], "\u4e2d\u6587\u503c")


if __name__ == "__main__":
    unittest.main()

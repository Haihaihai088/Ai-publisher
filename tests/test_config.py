# tests/test_config.py — 配置校验逻辑测试
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# 确保项目路径在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent / "ai_publisher"))

# Mock dotenv 避免需要安装依赖（必须在 import config 前注入）
_mock_dotenv = MagicMock()
sys.modules["dotenv"] = _mock_dotenv

# 模拟 .env 不存在的情况
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("OPENAI_BASE_URL", None)
os.environ.pop("OPENAI_MODEL", None)

import config


class TestValidateConfig(unittest.TestCase):

    def setUp(self):
        # 每个测试前清除环境变量，让 config 的默认值生效
        self._saved = {}
        for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
            self._saved[key] = os.environ.pop(key, None)

    def tearDown(self):
        for key, val in self._saved.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    def test_missing_api_key(self):
        config.AI_API_KEY = ""
        config.AI_BASE_URL = "https://api.deepseek.com/v1"
        config.AI_MODEL = "deepseek-chat"
        ok, errors = config.validate_config()
        self.assertFalse(ok)
        self.assertTrue(any("API_KEY" in e for e in errors))

    def test_invalid_base_url(self):
        config.AI_API_KEY = "sk-test"
        config.AI_BASE_URL = "not-a-url"
        config.AI_MODEL = "deepseek-chat"
        ok, errors = config.validate_config()
        self.assertFalse(ok)
        self.assertTrue(any("格式非法" in e for e in errors))

    def test_missing_model(self):
        config.AI_API_KEY = "sk-test"
        config.AI_BASE_URL = "https://api.deepseek.com/v1"
        config.AI_MODEL = ""
        ok, errors = config.validate_config()
        self.assertFalse(ok)
        self.assertTrue(any("MODEL" in e for e in errors))

    def test_valid_config(self):
        config.AI_API_KEY = "sk-test"
        config.AI_BASE_URL = "https://api.openai.com/v1"
        config.AI_MODEL = "gpt-4o-mini"
        ok, errors = config.validate_config()
        self.assertTrue(ok)
        self.assertEqual(len(errors), 0)

    def test_https_url_accepted(self):
        config.AI_API_KEY = "sk-test"
        config.AI_BASE_URL = "https://api.deepseek.com/v1"
        config.AI_MODEL = "deepseek-chat"
        ok, _ = config.validate_config()
        self.assertTrue(ok)

    def test_http_url_accepted(self):
        config.AI_API_KEY = "sk-test"
        config.AI_BASE_URL = "http://localhost:8080/v1"
        config.AI_MODEL = "deepseek-chat"
        ok, _ = config.validate_config()
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()

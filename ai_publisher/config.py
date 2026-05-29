# config.py - 全局配置管理
# 从 .env 文件读取所有配置，提供类型安全的访问接口

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# ─────────────────────────────────────────────
# 路径常量
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TASKS_DIR = DATA_DIR / "tasks"
COOKIES_DIR = DATA_DIR / "cookies"
UPLOADS_DIR = DATA_DIR / "uploads"

# 启动时自动创建必要目录
for _dir in [TASKS_DIR, COOKIES_DIR, UPLOADS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# AI API 配置
# ─────────────────────────────────────────────
AI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
AI_BASE_URL   = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
AI_MODEL      = os.getenv("OPENAI_MODEL", "deepseek-chat")

# ─────────────────────────────────────────────
# 平台配置
# ─────────────────────────────────────────────

# 平台显示名 → 内部 key 映射
PLATFORM_KEYS = {
    "小红书": "xiaohongshu",
    "知乎":   "zhihu",
    "贴吧":   "tieba",
    "公众号": "wechat",
}

# 需要每次手动扫码的平台（在审核队列里显示警告）
MANUAL_SCAN_PLATFORMS = {"wechat"}

# 各平台 Cookie 文件路径
def get_cookie_path(platform_key: str) -> Path:
    return COOKIES_DIR / f"{platform_key}.json"

# ─────────────────────────────────────────────
# 任务状态枚举（字符串常量，方便 JSON 存储）
# ─────────────────────────────────────────────
class TaskStatus:
    CREATED        = "created"         # 刚创建
    ANALYZING      = "analyzing"       # AI处理中
    PENDING_REVIEW = "pending_review"  # 等待人工审核
    PUBLISHING     = "publishing"      # 发布中
    COMPLETED      = "completed"       # 全部完成
    FAILED         = "failed"          # 发布失败

# 状态的中文显示名
STATUS_LABELS = {
    TaskStatus.CREATED:        "⏳ 等待处理",
    TaskStatus.ANALYZING:      "🤖 AI处理中",
    TaskStatus.PENDING_REVIEW: "📝 待审核",
    TaskStatus.PUBLISHING:     "🚀 发布中",
    TaskStatus.COMPLETED:      "✅ 已完成",
    TaskStatus.FAILED:         "❌ 失败",
}

# ─────────────────────────────────────────────
# 发布结果状态
# ─────────────────────────────────────────────
class PublishStatus:
    PENDING   = "pending"    # 待发布
    SUCCESS   = "success"    # 发布成功
    FAILED    = "failed"     # 发布失败
    SKIPPED   = "skipped"    # 用户跳过

# ─────────────────────────────────────────────
# Playwright 配置
# ─────────────────────────────────────────────
BROWSER_HEADLESS = False          # 发布时展示浏览器（方便调试和扫码）
BROWSER_SLOW_MO  = 500            # 操作间隔毫秒，太快容易被风控
PUBLISH_TIMEOUT  = 60_000         # 发布超时：60秒

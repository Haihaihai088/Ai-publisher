# utils/qrcode_utils.py - 登录二维码提取与保存
#
# 从 social-auto-upload/utils/login_qrcode.py 精简移植。
# 仅保留核心图片保存功能，不依赖 cv2 / segno 等重型库。

import base64
from datetime import datetime
from pathlib import Path


def build_qrcode_path(platform_key: str, profiles_dir: Path, suffix: str = "login_qrcode") -> Path:
    """生成带时间戳的二维码图片路径"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return profiles_dir / platform_key / f"{suffix}_{timestamp}.png"


def save_qrcode_image(data_url: str, output_path: Path) -> Path:
    """将 data:image URL (base64) 保存为 PNG 文件"""
    if not data_url.startswith("data:image/"):
        raise ValueError(f"不是 data:image 格式: {data_url[:60]}...")

    header, encoded = data_url.split(",", 1)
    if ";base64" not in header:
        raise ValueError("二维码图片不是 base64 编码")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(encoded))
    return output_path


def remove_qrcode_file(qrcode_path: Path | None) -> bool:
    """删除临时二维码文件"""
    if qrcode_path and qrcode_path.exists():
        qrcode_path.unlink()
        return True
    return False

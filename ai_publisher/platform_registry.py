# platform_registry.py - 平台注册表
#
# 所有平台定义的唯一数据源。
# 每个 publisher 模块 import 时自注册，消费者通过此类查询平台信息。
# 添加新平台只需：1) 新建 publishers/xxx.py  2) 在 __init__.py 中 import 即可。

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Type, Iterator

import config


@dataclass
class PlatformDescriptor:
    """描述一个发布平台的完整元数据"""

    # ── 基础身份 ──
    key: str                            # "xiaohongshu"
    name: str                           # "小红书"
    icon: str                           # "📕"
    publisher_class: Type               # XiaohongshuPublisher（类，非实例）
    login_url: str

    # ── 能力标志 ──
    needs_manual_scan: bool = False     # 每次发布都需要扫码
    skip_login_check: bool = False      # 不检查 is_logged_in()
    has_tags: bool = True               # AI 输出中包含 tags 字段
    has_bar_selection: bool = False     # 发布前需要用户选择社区/吧名
    needs_warning_in_review: bool = False  # 审核队列中显示额外警告

    # ── UI 定制 ──
    sidebar_btn_label: str = "登录"
    logged_in_label: str = "已登录"
    login_message: str = ""   # 为空时用默认文案
    review_warning: str = ""

    # ── AI 生成 ──
    ai_spec: str = ""         # 该平台的写作规范（注入到 prompt）
    output_schema: str = ""   # 该平台的输出 JSON 示例（注入到 prompt）

    # ── Cookie 文件名后缀（默认与 key 相同） ──
    cookie_suffix: Optional[str] = None


class PlatformRegistry:
    """平台注册表：单例式类，存储所有已注册平台"""

    _platforms: dict[str, PlatformDescriptor] = {}
    simulated_mode: bool = False
    _initialized: bool = False

    @classmethod
    def register(cls, desc: PlatformDescriptor):
        """注册一个平台（由 publisher 模块在 import 时调用）"""
        # 同步 publisher 类的属性到 descriptor
        pub_cls = desc.publisher_class
        if hasattr(pub_cls, "needs_manual_scan"):
            for attr in (
                "needs_manual_scan", "skip_login_check", "has_tags",
                "has_bar_selection", "needs_warning_in_review",
                "icon", "sidebar_btn_label", "logged_in_label",
                "login_message", "review_warning",
            ):
                if hasattr(pub_cls, attr) and getattr(desc, attr) == getattr(PlatformDescriptor, attr, None):
                    setattr(desc, attr, getattr(pub_cls, attr))

        cls._platforms[desc.key] = desc
        cls._initialized = True

    @classmethod
    def get(cls, key: str) -> Optional[PlatformDescriptor]:
        """根据 key 获取平台描述"""
        return cls._platforms.get(key)

    @classmethod
    def all(cls) -> dict[str, PlatformDescriptor]:
        """返回所有已注册平台"""
        return dict(cls._platforms)

    @classmethod
    def items(cls) -> Iterator[tuple[str, PlatformDescriptor]]:
        """遍历所有平台"""
        return iter(cls._platforms.items())

    @classmethod
    def keys(cls) -> list[str]:
        """所有平台 key"""
        return list(cls._platforms.keys())

    @classmethod
    def name_to_key(cls, name: str) -> Optional[str]:
        """中文名 → key"""
        for d in cls._platforms.values():
            if d.name == name:
                return d.key
        return None

    @classmethod
    def key_to_name(cls, key: str) -> str:
        """key → 中文名"""
        d = cls.get(key)
        return d.name if d else key

    @classmethod
    def get_ai_specs(cls, platforms: list[str]) -> str:
        """拼接指定平台的写作规范（用于 AI prompt）"""
        specs = []
        for p in platforms:
            d = cls.get(p)
            if d and d.ai_spec:
                specs.append(f"【{d.name}】{d.ai_spec}")
        return "\n".join(specs)

    @classmethod
    def get_output_schema(cls, platforms: list[str]) -> str:
        """拼接指定平台的输出 JSON 结构示例"""
        schemas = []
        for p in platforms:
            d = cls.get(p)
            if d and d.output_schema:
                schemas.append(d.output_schema)
        return ",\n".join(schemas)

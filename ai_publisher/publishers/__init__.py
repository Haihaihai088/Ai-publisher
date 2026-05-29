# 导入所有发布器模块以触发 PlatformRegistry.register()
# 之后通过 PlatformRegistry.all() 查询所有已注册平台

from . import xiaohongshu
from . import zhihu
from . import tieba
from . import wechat
from . import mock

# 向后兼容：保留类名直接导入
from .xiaohongshu import XiaohongshuPublisher
from .zhihu import ZhihuPublisher
from .tieba import TiebaPublisher
from .wechat import WechatPublisher
from .mock import MockPublisher

__all__ = [
    "XiaohongshuPublisher", "ZhihuPublisher", "TiebaPublisher",
    "WechatPublisher", "MockPublisher",
]

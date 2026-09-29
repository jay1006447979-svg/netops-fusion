"""厂商插件层 — 导入所有生成器以触发注册"""

from app.vendors.base import BaseConfigGenerator
from app.vendors.huawei import HuaweiGenerator
from app.vendors.h3c import H3CGenerator
from app.vendors.ruijie import RuijieGenerator
from app.vendors.maipu import MaipuGenerator

__all__ = [
    "BaseConfigGenerator",
    "HuaweiGenerator",
    "H3CGenerator",
    "RuijieGenerator",
    "MaipuGenerator",
]

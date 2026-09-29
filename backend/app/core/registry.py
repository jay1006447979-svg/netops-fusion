"""厂商插件注册表 — 新增厂商只需实现生成器并用装饰器注册，零改动核心代码"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Type

if TYPE_CHECKING:
    from app.vendors.base import BaseConfigGenerator


class VendorRegistry:
    """厂商注册表单例

    用法:
        @vendor_registry.register("huawei", device_types=["switch", "router", "ap"])
        class HuaweiGenerator(BaseConfigGenerator):
            ...
    """

    _instance: Optional["VendorRegistry"] = None

    def __new__(cls) -> "VendorRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._registry: Dict[str, dict] = {}
        return cls._instance

    def register(self, vendor: str, device_types: Optional[List[str]] = None):
        """装饰器: 注册一个厂商配置生成器"""

        def decorator(generator_cls):
            self._registry[vendor] = {
                "vendor": vendor,
                "class": generator_cls,
                "device_types": device_types or ["switch"],
            }
            return generator_cls

        return decorator

    def get_generator(self, vendor: str):
        entry = self._registry.get(vendor)
        if entry is None:
            raise ValueError(
                f"不支持的厂商: {vendor}, 当前支持: {self.list_vendors()}"
            )
        return entry["class"]()

    def list_vendors(self) -> List[str]:
        return sorted(self._registry.keys())

    def get_vendor_info(self, vendor: str) -> Optional[dict]:
        return self._registry.get(vendor)

    def list_all_info(self) -> List[dict]:
        result = []
        for vendor in sorted(self._registry.keys()):
            info = self._registry[vendor]
            result.append(
                {
                    "vendor": info["vendor"],
                    "device_types": info["device_types"],
                }
            )
        return result


vendor_registry = VendorRegistry()

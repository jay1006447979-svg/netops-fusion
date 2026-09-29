"""配置生成服务 — 工厂入口, 调用厂商注册表分发"""

from __future__ import annotations

from app.core.registry import vendor_registry
from app.models.device import DeviceConfig
from app.services.config_validator import validator
import app.vendors  # noqa: F401 — 确保厂商生成器被注册


class ConfigGeneratorService:
    """配置生成服务"""

    def generate(self, device_config: DeviceConfig) -> dict:
        """生成配置, 返回 {config_text, vendor, validation}"""
        validation = validator.validate(device_config.to_flat_dict())

        vendor_str = (
            device_config.vendor.value
            if hasattr(device_config.vendor, "value")
            else str(device_config.vendor)
        )
        generator = vendor_registry.get_generator(vendor_str)
        config_text = generator.generate_all(device_config)

        return {
            "config_text": config_text,
            "vendor": vendor_str,
            "device_type": device_config.device_type.value
            if hasattr(device_config.device_type, "value")
            else str(device_config.device_type),
            "hostname": device_config.hostname,
            "validation": validation,
        }

    def list_vendors(self) -> list[dict]:
        return vendor_registry.list_all_info()


config_service = ConfigGeneratorService()

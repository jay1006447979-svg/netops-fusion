"""配置生成器基类 — 定义厂商生成器接口

每个厂商子类需实现以下方法, 返回配置字符串:
  generate_basic / generate_vlan / generate_routing
  generate_security / generate_interface / generate_all
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.device import DeviceConfig


class BaseConfigGenerator(ABC):
    """厂商配置生成器抽象基类"""

    vendor: str = "base"

    @abstractmethod
    def generate_basic(self, config: dict) -> str:
        ...

    @abstractmethod
    def generate_vlan(self, config: dict) -> str:
        ...

    @abstractmethod
    def generate_routing(self, config: dict) -> str:
        ...

    @abstractmethod
    def generate_security(self, config: dict) -> str:
        ...

    @abstractmethod
    def generate_interface(self, config: dict) -> str:
        ...

    def generate_all(self, device_config: DeviceConfig) -> str:
        """生成完整配置 — 通用流程, 子类可覆盖"""
        data = device_config.to_flat_dict()
        header = (
            f"#\n"
            f"# {self.vendor.upper()} {device_config.device_type.value} 配置\n"
            f"# 由 NetOps Fusion 生成\n"
            f"#\n\n"
        )
        sections = [header]
        if device_config.basic or device_config.hostname:
            sections.append(self.generate_basic(data.get("basic", {})))
        if device_config.vlan:
            sections.append(self.generate_vlan(data.get("vlan", {})))
        if device_config.routing:
            sections.append(self.generate_routing(data.get("routing", {})))
        if device_config.security:
            sections.append(self.generate_security(data.get("security", {})))
        if device_config.interface:
            sections.append(self.generate_interface(data.get("interface", {})))
        return "".join(sections)

    @staticmethod
    def _vlan_range_str(vlan_ids: list[int]) -> str:
        """将 VLAN 列表转为 '1 to 5 10 20 to 30' 格式"""
        if not vlan_ids:
            return ""
        sorted_v = sorted(set(vlan_ids))
        ranges = []
        start = end = sorted_v[0]
        for v in sorted_v[1:]:
            if v == end + 1:
                end = v
            else:
                ranges.append(str(start) if start == end else f"{start} to {end}")
                start = end = v
        ranges.append(str(start) if start == end else f"{start} to {end}")
        return " ".join(ranges)

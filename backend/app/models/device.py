"""设备配置顶层模型 — 聚合所有配置模块"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.models.basic import BasicConfig
from app.models.interface import InterfaceFullConfig
from app.models.routing import RoutingFullConfig
from app.models.security import SecurityFullConfig
from app.models.vlan import VlanFullConfig


class Vendor(str, Enum):
    huawei = "huawei"
    h3c = "h3c"
    ruijie = "ruijie"
    maipu = "maipu"


class DeviceType(str, Enum):
    switch = "switch"
    router = "router"
    ap = "ap"
    ac = "ac"        # 无线控制器
    wan = "wan"      # 外网/出口示意
    pc = "pc"        # 终端 PC
    ipc = "ipc"      # 网络摄像头
    custom = "custom"  # 自定义设备(示意图标)


class DeviceConfig(BaseModel):
    """完整设备配置 — 对应一次配置生成请求"""

    vendor: Vendor = Vendor.huawei
    device_type: DeviceType = DeviceType.switch
    hostname: Optional[str] = Field(None, max_length=32)

    basic: Optional[BasicConfig] = None
    vlan: Optional[VlanFullConfig] = None
    routing: Optional[RoutingFullConfig] = None
    security: Optional[SecurityFullConfig] = None
    interface: Optional[InterfaceFullConfig] = None

    def to_flat_dict(self) -> dict:
        """转为扁平字典, 兼容旧式生成器入参"""
        data = self.model_dump(exclude_none=True)
        if self.hostname:
            data.setdefault("basic", {})["hostname"] = self.hostname
        return data

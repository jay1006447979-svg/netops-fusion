"""接口配置数据模型"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class EthTrunkConfig(BaseModel):
    trunk_id: int = Field(..., ge=1, le=128)
    mode: str = Field("lacp-static", description="manual/lacp-static/lacp-dynamic")
    member_ports: Optional[List[str]] = None
    description: Optional[str] = None
    port_link_type: str = "trunk"
    trunk_vlans: Optional[List[int]] = None
    native_vlan: Optional[int] = Field(None, ge=1, le=4094)


class LacpConfig(BaseModel):
    priority: int = Field(32768, ge=0, le=65535)
    system_id: Optional[str] = None
    fast_switchover: bool = True


class LldpConfig(BaseModel):
    enable: bool = Field(False, description="是否启用 LLDP")
    mode: str = Field("both", description="both/tx/rx")
    interval: int = Field(30, ge=1)
    holdtime: int = Field(120, ge=1, description="LLDP 存活时间(秒)")
    fast_count: int = Field(4, ge=1)
    interfaces: Optional[List[dict]] = None


class PoeGlobalConfig(BaseModel):
    enable: bool = Field(False, description="是否启用 PoE")
    max_power: int = Field(74000, ge=0)
    legacy_enable: bool = False
    interfaces: Optional[List[dict]] = None


class PortIsolationConfig(BaseModel):
    enable: bool = Field(False, description="是否启用端口隔离")
    group_id: int = Field(1, ge=1)
    interfaces: Optional[List[str]] = None


class LoopbackDetectionConfig(BaseModel):
    enable: bool = Field(False, description="是否启用环路检测")
    interval: int = Field(5, ge=1)
    action: str = Field("block", description="block/none/trap-to-cpu/shutdown")
    vlan_ids: Optional[List[int]] = Field(None, description="检测的 VLAN 列表")


class RateLimitConfig(BaseModel):
    interface: str
    cir_in: Optional[int] = Field(None, ge=8, le=4294967295)
    cir_out: Optional[int] = Field(None, ge=8, le=4294967295)


class InterfaceQosConfig(BaseModel):
    interface: str
    car_inbound: Optional[int] = None
    car_outbound: Optional[int] = None
    priority: Optional[int] = Field(None, ge=0, le=7)


class InterfaceFullConfig(BaseModel):
    eth_trunks: Optional[List[EthTrunkConfig]] = None
    lacp: Optional[LacpConfig] = None
    lldp: Optional[LldpConfig] = None
    poe: Optional[PoeGlobalConfig] = None
    port_isolation: Optional[PortIsolationConfig] = None
    loopback_detection: Optional[LoopbackDetectionConfig] = None
    rate_limits: Optional[List[RateLimitConfig]] = None
    interface_qos: Optional[List[InterfaceQosConfig]] = None

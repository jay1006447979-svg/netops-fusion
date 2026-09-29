"""VLAN 配置数据模型"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class VlanConfig(BaseModel):
    id: int = Field(..., ge=1, le=4094, description="VLAN ID")
    name: Optional[str] = Field(None, max_length=32)
    description: Optional[str] = None


class InterfaceVlanConfig(BaseModel):
    interface: str
    type: str = Field("access", description="access/trunk/hybrid")
    vlan_id: Optional[int] = Field(None, ge=1, le=4094)
    trunk_vlans: Optional[List[int]] = None
    pvid: Optional[int] = Field(None, ge=1, le=4094)
    untagged_vlans: Optional[List[int]] = None
    tagged_vlans: Optional[List[int]] = None


class VlanifConfig(BaseModel):
    vlan_id: int = Field(..., ge=1, le=4094)
    ip_address: str
    mask: str = "255.255.255.0"
    description: Optional[str] = None


class VoiceVlanConfig(BaseModel):
    interface: str
    vlan_id: int = Field(..., ge=1, le=4094)
    untagged: bool = True


class StpConfig(BaseModel):
    mode: str = "stp"
    priority: int = Field(32768, ge=0, le=61440)
    enable: bool = Field(False, description="是否启用 STP")


class VlanFullConfig(BaseModel):
    vlans: Optional[List[VlanConfig]] = None
    interfaces: Optional[List[InterfaceVlanConfig]] = None
    vlanifs: Optional[List[VlanifConfig]] = None
    voice_vlans: Optional[List[VoiceVlanConfig]] = None
    stp: Optional[StpConfig] = None

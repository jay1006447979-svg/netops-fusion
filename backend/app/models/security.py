"""安全配置数据模型"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AclRuleConfig(BaseModel):
    rule_id: int = Field(..., ge=0)
    action: str = Field("permit", description="permit/deny")
    protocol: str = Field("ip", description="ip/tcp/udp/icmp")
    source: str = "any"
    source_wildcard: str = "0.0.0.0"
    destination: str = "any"
    dest_wildcard: str = "0.0.0.0"
    dest_port: Optional[int] = Field(None, ge=1, le=65535)


class AclConfig(BaseModel):
    number: int = Field(..., ge=2000, le=5999)
    description: Optional[str] = None
    rules: Optional[List[AclRuleConfig]] = None


class PortSecurityConfig(BaseModel):
    interface: str
    max_mac: int = Field(1, ge=1)
    protect_action: str = Field("protect", description="protect/restrict/shutdown")
    sticky: bool = True
    mac_address: Optional[str] = None
    vlan_id: Optional[int] = Field(None, ge=1, le=4094)


class MacBindingConfig(BaseModel):
    interface: str
    mac_address: str
    vlan_id: int = Field(..., ge=1, le=4094)


class StaticMacConfig(BaseModel):
    mac_address: str
    interface: str
    vlan_id: int = Field(..., ge=1, le=4094)


class BlackholeMacConfig(BaseModel):
    mac_address: str


class MacLimitConfig(BaseModel):
    limit: int = Field(100, ge=1)
    vlan: Optional[int] = Field(None, ge=1, le=4094)
    interface: Optional[str] = None
    action: str = "discard"
    alarm: bool = True


class Dot1xGlobalConfig(BaseModel):
    enable: bool = Field(False, description="是否启用 802.1X")
    method: str = Field("chap", description="chap/pap/eap")
    reauth_period: int = Field(3600, ge=60)
    tx_period: int = Field(30, ge=1)


class Dot1xInterfaceConfig(BaseModel):
    interface: str
    enable: bool = True
    port_method: str = Field("mac", description="mac/port")
    max_users: int = Field(256, ge=1)
    quiet_period: int = Field(60, ge=1)


class ArpProtectionConfig(BaseModel):
    vlans: Optional[List[int]] = None
    trust_ports: Optional[List[str]] = None


class StaticArpConfig(BaseModel):
    ip_address: str
    mac_address: str
    vlan_id: Optional[int] = Field(None, ge=1, le=4094)
    interface: Optional[str] = None


class ArpLimitConfig(BaseModel):
    limit: int = Field(100, ge=1)
    interface: Optional[str] = None
    vlan: Optional[int] = Field(None, ge=1, le=4094)


class RadiusServerConfig(BaseModel):
    server_name: str
    shared_key: str
    ip_address: str
    auth_port: int = Field(1812, ge=1, le=65535)
    acct_port: int = Field(1813, ge=1, le=65535)
    retransmit: int = Field(3, ge=1)
    timeout: int = Field(5, ge=1)


class DhcpSnoopingConfig(BaseModel):
    enable: bool = Field(False, description="是否启用 DHCP Snooping")
    vlans: Optional[List[int]] = None
    trust_ports: Optional[List[str]] = None


class StormControlConfig(BaseModel):
    interface: str
    broadcast: Optional[int] = None
    multicast: Optional[int] = None
    unicast: Optional[int] = None
    action: str = "block"


class TrafficFilterConfig(BaseModel):
    interface: str
    direction: str = Field("inbound", description="inbound/outbound")
    acl_number: int = Field(..., ge=2000, le=5999)


class UserBindConfig(BaseModel):
    interface: str
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    vlan_id: Optional[int] = Field(None, ge=1, le=4094)


class SecurityFullConfig(BaseModel):
    acls: Optional[List[AclConfig]] = None
    port_security: Optional[List[PortSecurityConfig]] = None
    mac_bindings: Optional[List[MacBindingConfig]] = None
    static_macs: Optional[List[StaticMacConfig]] = None
    blackhole_macs: Optional[List[BlackholeMacConfig]] = None
    mac_limits: Optional[List[MacLimitConfig]] = None
    dot1x_global: Optional[Dot1xGlobalConfig] = None
    dot1x_interfaces: Optional[List[Dot1xInterfaceConfig]] = None
    arp_protection: Optional[ArpProtectionConfig] = None
    static_arps: Optional[List[StaticArpConfig]] = None
    arp_limits: Optional[List[ArpLimitConfig]] = None
    radius_servers: Optional[List[RadiusServerConfig]] = None
    dhcp_snooping: Optional[DhcpSnoopingConfig] = None
    storm_controls: Optional[List[StormControlConfig]] = None
    traffic_filters: Optional[List[TrafficFilterConfig]] = None
    user_binds: Optional[List[UserBindConfig]] = None

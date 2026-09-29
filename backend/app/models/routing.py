"""路由配置数据模型"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class StaticRouteConfig(BaseModel):
    dest_network: str
    mask: str
    next_hop: Optional[str] = None
    interface: Optional[str] = None
    preference: Optional[int] = Field(None, ge=1, le=255)


class DefaultRouteConfig(BaseModel):
    next_hop: Optional[str] = None
    interface: Optional[str] = None


class OspfNetworkConfig(BaseModel):
    address: str
    mask: str = "0.0.0.255"
    area: str = "0"


class OspfConfig(BaseModel):
    process_id: int = Field(1, ge=1)
    router_id: Optional[str] = None
    area_id: str = "0"
    networks: Optional[List[OspfNetworkConfig]] = None
    interfaces: Optional[List[str]] = None
    cost: Optional[int] = Field(None, ge=1, le=65535)


class OspfInterfaceConfig(BaseModel):
    interface: str
    cost: Optional[int] = Field(None, ge=1, le=65535)
    priority: Optional[int] = Field(None, ge=0, le=255)
    hello_time: int = Field(10, ge=1)
    dead_time: int = Field(40, ge=1)
    area: Optional[str] = None


class BgpPeerConfig(BaseModel):
    ip: str
    as_number: int = Field(..., ge=1, le=4294967295)


class BgpImportRouteConfig(BaseModel):
    protocol: str = "ospf"
    process: int = 1


class BgpConfig(BaseModel):
    as_number: int = Field(..., ge=1, le=4294967295)
    router_id: Optional[str] = None
    peers: Optional[List[BgpPeerConfig]] = None
    networks: Optional[List[str]] = None
    import_routes: Optional[List[BgpImportRouteConfig]] = None


class RipConfig(BaseModel):
    version: int = Field(2, ge=1, le=2)
    networks: Optional[List[str]] = None
    import_routes: Optional[List[str]] = None


class RoutingFullConfig(BaseModel):
    static_routes: Optional[List[StaticRouteConfig]] = None
    default_route: Optional[DefaultRouteConfig] = None
    ospf: Optional[OspfConfig] = None
    ospf_interfaces: Optional[List[OspfInterfaceConfig]] = None
    bgp: Optional[BgpConfig] = None
    rip: Optional[RipConfig] = None

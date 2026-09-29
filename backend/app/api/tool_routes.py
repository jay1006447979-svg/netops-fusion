"""网络工具 API"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.tools.subnet_calculator import subnet_calculator
from app.tools.ping_tool import ping_tool
from app.tools.port_scanner import port_scanner
from app.tools.traceroute import trace_route
from app.tools.dns_tool import dns_tool
from app.tools.network_info import network_info
from app.tools.config_compare import config_compare
from app.tools.config_io import config_io

router = APIRouter(prefix="/api/tools", tags=["网络工具"])


# ======================== 子网计算器 ========================
class SubnetRequest(BaseModel):
    ip: str
    mask: str = "24"


@router.post("/subnet/calculate")
async def subnet_calculate(req: SubnetRequest):
    """子网计算"""
    return {"success": True, "result": subnet_calculator.calculate(req.ip, req.mask)}


class SubnetDivideRequest(BaseModel):
    ip: str
    prefix: int
    new_prefix: int


@router.post("/subnet/divide")
async def subnet_divide(req: SubnetDivideRequest):
    """子网划分"""
    return {"success": True, "subnets": subnet_calculator.subnet_divide(req.ip, req.prefix, req.new_prefix)}


class IpRangeRequest(BaseModel):
    start: str
    end: str


@router.post("/subnet/ip-range-to-cidr")
async def ip_range_to_cidr(req: IpRangeRequest):
    """IP范围转CIDR"""
    return {"success": True, "cidrs": subnet_calculator.ip_range_to_cidr(req.start, req.end)}


class IpConvertRequest(BaseModel):
    ip: str
    target: str = "binary"


@router.post("/subnet/ip-convert")
async def ip_convert(req: IpConvertRequest):
    """IP格式转换"""
    return {"success": True, "result": subnet_calculator.convert_ip_format(req.ip, req.target)}


# ======================== Ping ========================
class PingRequest(BaseModel):
    host: str
    count: int = 4
    timeout: int = 2


@router.post("/ping")
async def ping(req: PingRequest):
    """单主机Ping"""
    return {"success": True, "result": await ping_tool.ping(req.host, req.count, req.timeout)}


class PingBatchRequest(BaseModel):
    hosts: list[str]
    count: int = 2


@router.post("/ping/batch")
async def ping_batch(req: PingBatchRequest):
    """批量Ping"""
    return {"success": True, "results": await ping_tool.ping_batch(req.hosts, req.count)}


class PingScanRequest(BaseModel):
    network: str
    timeout: int = 1


@router.post("/ping/scan")
async def ping_scan(req: PingScanRequest):
    """Ping扫描网段"""
    return {"success": True, "results": await ping_tool.ping_scan(req.network, req.timeout)}


# ======================== 端口扫描 ========================
class PortScanRequest(BaseModel):
    host: str
    ports: list[int] | None = None
    timeout: float = 2.0


@router.post("/port-scan")
async def port_scan(req: PortScanRequest):
    """端口扫描"""
    results = await port_scanner.scan(req.host, req.ports, req.timeout)
    return {"success": True, "open_ports": results}


class PortScanRangeRequest(BaseModel):
    host: str
    start: int = 1
    end: int = 1024
    timeout: float = 1.0


@router.post("/port-scan/range")
async def port_scan_range(req: PortScanRangeRequest):
    """端口范围扫描"""
    results = await port_scanner.scan_range(req.host, req.start, req.end, req.timeout)
    return {"success": True, "open_ports": results}


class PortTestRequest(BaseModel):
    host: str
    port: int
    timeout: float = 3.0


@router.post("/port-test")
async def port_test(req: PortTestRequest):
    """快速端口测试"""
    return {"success": True, "result": await port_scanner.quick_test(req.host, req.port, req.timeout)}


# ======================== 路由跟踪 ========================
class TraceRequest(BaseModel):
    host: str
    max_hops: int = 30
    timeout: int = 3


@router.post("/traceroute")
async def traceroute(req: TraceRequest):
    """路由跟踪"""
    return {"success": True, "hops": await trace_route.trace(req.host, req.max_hops, req.timeout)}


# ======================== DNS/Whois ========================
@router.get("/dns/{domain}")
async def dns_lookup(domain: str, record_type: str = Query("A")):
    """DNS查询"""
    return {"success": True, "results": await dns_tool.dns_lookup(domain, record_type)}


@router.get("/reverse-dns/{ip}")
async def reverse_dns(ip: str):
    """反向DNS查询"""
    return {"success": True, "results": await dns_tool.reverse_dns(ip)}


@router.get("/whois/{domain}")
async def whois(domain: str):
    """Whois查询"""
    return {"success": True, "result": await dns_tool.whois(domain)}


# ======================== 网络信息 ========================
@router.get("/network-info/local")
async def local_info():
    """本机IP信息"""
    return {"success": True, "info": network_info.get_local_ip()}


@router.get("/network-info/public-ip")
async def public_ip():
    """公网IP查询"""
    return {"success": True, "info": await network_info.get_public_ip()}


# ======================== 配置比较 ========================
class CompareRequest(BaseModel):
    config1: str
    config2: str
    context: int = 3


@router.post("/config-compare")
async def config_compare_tool(req: CompareRequest):
    """配置差异对比"""
    return {"success": True, "result": config_compare.compare(req.config1, req.config2, req.context)}


class ConvertRequest(BaseModel):
    config: str
    from_vendor: str = "huawei"
    to_vendor: str = "h3c"


@router.post("/config-convert")
async def config_convert(req: ConvertRequest):
    """华为/H3C命令转换"""
    from app.services.manual_service import manual_service

    result = manual_service.convert_config(req.config, req.from_vendor, req.to_vendor)
    return {"success": True, "result": result}


# ======================== 配置导入导出 ========================
class ImportJsonRequest(BaseModel):
    json_str: str


@router.post("/config-import/json")
async def import_json(req: ImportJsonRequest):
    """从JSON导入配置"""
    return {"success": True, "config": config_io.import_json(req.json_str)}


class ParseConfigRequest(BaseModel):
    config_text: str


@router.post("/config-parse")
async def parse_config(req: ParseConfigRequest):
    """解析配置文本"""
    return {"success": True, "parsed": config_io.parse_config_text(req.config_text)}

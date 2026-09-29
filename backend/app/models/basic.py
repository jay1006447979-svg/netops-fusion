"""基础配置数据模型"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PasswordConfig(BaseModel):
    value: str = Field(..., description="密码值")
    encrypted: bool = Field(False, description="是否加密存储")


class ConsoleConfig(BaseModel):
    enable: bool = Field(False, description="是否启用 Console 认证配置")
    password: Optional[str] = None
    authentication: str = Field("password", description="认证方式: password/aaa")
    idle_timeout: int = Field(10, ge=0, le=35791)


class BannerConfig(BaseModel):
    motd: Optional[str] = None
    login: Optional[str] = None


class UserConfig(BaseModel):
    enable: bool = Field(False, description="是否启用本地用户管理")
    username: str = "admin"
    password: str = "admin@123"
    level: int = Field(15, ge=0, le=15)
    encrypted: bool = False
    service_types: List[str] = Field(
        default_factory=lambda: ["terminal", "ssh", "telnet"]
    )


class NtpServerConfig(BaseModel):
    ip: str
    prefer: bool = False


class NtpConfig(BaseModel):
    enable: bool = Field(False, description="是否启用 NTP 配置")
    servers: Optional[List[NtpServerConfig]] = None
    timezone: str = "UTC+8"
    broadcast_enable: bool = False


class SnmpConfig(BaseModel):
    enable: bool = Field(False, description="是否启用 SNMP 配置")
    version: str = "v2c"
    community_read: Optional[str] = None
    community_write: Optional[str] = None
    sys_name: Optional[str] = None
    sys_location: Optional[str] = None
    sys_contact: Optional[str] = None
    trap_enable: bool = False
    trap_host: Optional[str] = None


class LogConfig(BaseModel):
    host: Optional[str] = None
    info_center_enable: bool = True
    log_level: str = "informational"
    time_stamp: str = "date"


class MgmtInterfaceConfig(BaseModel):
    enable: bool = Field(False, description="是否启用管理接口配置")
    interface: str = "Vlanif1"
    ip_address: Optional[str] = None
    mask: str = "255.255.255.0"
    gateway: Optional[str] = None
    description: str = "Management Interface"


class DhcpGlobalConfig(BaseModel):
    enable: bool = True
    excluded_ips: Optional[List[dict]] = None
    dns_servers: Optional[List[str]] = None


class DnsConfig(BaseModel):
    enable: bool = Field(False, description="是否启用 DNS 配置")
    servers: Optional[List[str]] = None
    domain: Optional[str] = None
    resolve_enable: bool = False


class SshConfig(BaseModel):
    enable: bool = Field(False, description="是否启用 SSH 服务")
    version: int = Field(2, ge=1, le=2)
    port: int = Field(22, ge=1, le=65535)
    timeout: int = Field(60, ge=1)
    max_auth_tries: int = Field(5, ge=1)
    rekey_interval: int = Field(60, ge=1)


class TelnetConfig(BaseModel):
    enable: bool = Field(False, description="是否启用 Telnet 服务")


class BasicConfig(BaseModel):
    hostname: Optional[str] = Field(None, max_length=32)
    password: Optional[PasswordConfig] = None
    ssh: Optional[SshConfig] = None
    telnet: Optional[TelnetConfig] = None
    console: Optional[ConsoleConfig] = None
    banner: Optional[BannerConfig] = None
    user: Optional[UserConfig] = None
    ntp: Optional[NtpConfig] = None
    snmp: Optional[SnmpConfig] = None
    log: Optional[LogConfig] = None
    mgmt_interface: Optional[MgmtInterfaceConfig] = None
    dhcp_global: Optional[DhcpGlobalConfig] = None
    dns: Optional[DnsConfig] = None

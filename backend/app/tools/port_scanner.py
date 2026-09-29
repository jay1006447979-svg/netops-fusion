"""异步端口扫描工具"""

from __future__ import annotations

import asyncio
import socket
from typing import Optional


COMMON_PORTS = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    161: "SNMP",
    162: "SNMP-Trap",
    389: "LDAP",
    443: "HTTPS",
    636: "LDAPS",
    873: "Rsync",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    1521: "Oracle",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
    5900: "VNC",
    6379: "Redis",
    8080: "HTTP-Proxy",
    8443: "HTTPS-Alt",
    9200: "Elasticsearch",
    11211: "Memcached",
    27017: "MongoDB",
}


class PortScanner:
    """异步端口扫描"""

    @staticmethod
    async def scan_port(host: str, port: int, timeout: float = 2.0) -> dict:
        """扫描单个端口"""
        try:
            fut = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(fut, timeout=timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            service = COMMON_PORTS.get(port, "unknown")
            return {"port": port, "open": True, "service": service}
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return {"port": port, "open": False, "service": COMMON_PORTS.get(port, "")}

    @staticmethod
    async def scan(host: str, ports: Optional[list[int]] = None, timeout: float = 2.0) -> list[dict]:
        """扫描多个端口"""
        if ports is None:
            ports = sorted(COMMON_PORTS.keys())

        sem = asyncio.Semaphore(100)

        async def scan_with_sem(port: int) -> dict:
            async with sem:
                return await PortScanner.scan_port(host, port, timeout)

        tasks = [scan_with_sem(p) for p in ports]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r["open"]]

    @staticmethod
    async def scan_range(host: str, start: int = 1, end: int = 1024, timeout: float = 1.0) -> list[dict]:
        """扫描端口范围"""
        ports = list(range(start, end + 1))
        return await PortScanner.scan(host, ports, timeout)

    @staticmethod
    async def quick_test(host: str, port: int, timeout: float = 3.0) -> dict:
        """快速端口测试"""
        return await PortScanner.scan_port(host, port, timeout)


port_scanner = PortScanner()

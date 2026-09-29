"""DNS/Whois 查询工具"""

from __future__ import annotations

import asyncio
import socket
from typing import Optional


class DnsTool:
    """DNS查询、反向DNS、Whois"""

    @staticmethod
    async def dns_lookup(domain: str, record_type: str = "A") -> list[str]:
        """DNS查询"""
        try:
            loop = asyncio.get_event_loop()
            if record_type == "A":
                results = await loop.getaddrinfo(domain, None)
                return list({r[4][0] for r in results})
            elif record_type == "PTR":
                return await DnsTool.reverse_dns(domain)
            elif record_type == "MX":
                import dns.resolver  # type: ignore

                def _mx():
                    answers = dns.resolver.resolve(domain, "MX")
                    return [str(r.exchange) for r in answers]

                return await loop.run_in_executor(None, _mx)
            elif record_type == "CNAME":
                import dns.resolver  # type: ignore

                def _cname():
                    answers = dns.resolver.resolve(domain, "CNAME")
                    return [str(r.target) for r in answers]

                return await loop.run_in_executor(None, _cname)
            else:
                return []
        except ImportError:
            return ["error: dnspython 未安装, 仅支持A/PTR记录"]
        except Exception as e:
            return [f"error: {e}"]

    @staticmethod
    async def reverse_dns(ip: str) -> list[str]:
        """反向DNS查询"""
        try:
            loop = asyncio.get_event_loop()
            # Windows ProactorEventLoop 没有 gethostbyaddr，用 executor 跑同步版本
            hostname = await loop.run_in_executor(None, socket.gethostbyaddr, ip)
            return [hostname[0]]
        except socket.herror:
            return ["未找到PTR记录"]
        except Exception as e:
            return [f"error: {e}"]

    @staticmethod
    async def whois(domain: str) -> str:
        """Whois查询"""
        try:
            reader, writer = await asyncio.open_connection("whois.iana.org", 43)
            writer.write((domain + "\r\n").encode())
            await writer.drain()
            data = await reader.read(4096)
            writer.close()
            await writer.wait_closed()
            return data.decode(errors="ignore")
        except Exception as e:
            return f"error: {e}"


dns_tool = DnsTool()

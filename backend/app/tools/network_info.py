"""网络信息工具 — 本机IP/公网IP查询"""

from __future__ import annotations

import socket
import asyncio
import urllib.request


class NetworkInfo:
    """网络信息查询"""

    @staticmethod
    def get_local_ip() -> dict:
        """获取本机IP"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "127.0.0.1"

        hostname = socket.gethostname()

        all_ips = []
        try:
            all_ips = socket.getaddrinfo(hostname, None, socket.AF_INET)
            all_ips = list({addr[4][0] for addr in all_ips})
        except Exception:
            pass

        return {
            "hostname": hostname,
            "local_ip": local_ip,
            "all_ips": all_ips,
        }

    @staticmethod
    async def get_public_ip() -> dict:
        """获取公网IP"""
        import urllib.request

        def _fetch():
            try:
                with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5) as resp:
                    import json

                    return json.loads(resp.read().decode())
            except Exception:
                try:
                    with urllib.request.urlopen("https://httpbin.org/ip", timeout=5) as resp:
                        import json

                        return json.loads(resp.read().decode())
                except Exception as e:
                    return {"error": str(e)}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _fetch)


network_info = NetworkInfo()

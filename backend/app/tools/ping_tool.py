"""异步 Ping 工具 — 单主机/批量Ping/Ping扫描

Windows 兼容性：使用 subprocess.run + ThreadPoolExecutor + shell=True
避免 ProactorEventLoop 下 create_subprocess_exec 无法捕获控制台程序输出的问题。
"""

from __future__ import annotations

import asyncio
import platform
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor


class PingTool:
    """异步Ping工具"""

    _executor = ThreadPoolExecutor(max_workers=20)

    @staticmethod
    def _build_ping_cmd(host: str, count: int = 1, timeout: int = 2) -> str:
        """构建平台相关的 ping 命令字符串"""
        if platform.system() == "Windows":
            # Windows: -n=count, -w=timeout(ms)
            return f'ping -n {count} -w {timeout * 1000} {host}'
        else:
            # Linux/macOS: -c=count, -W=timeout(s)
            return f'ping -c {count} -W {timeout} {host}'

    @staticmethod
    def _run_ping_sync(host: str, count: int = 1, timeout: int = 2) -> tuple[str, int]:
        """同步执行 ping 命令，返回 (stdout文本, returncode)"""
        cmd = PingTool._build_ping_cmd(host, count, timeout)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=count * timeout + 10,
            shell=True,
            encoding="gbk" if platform.system() == "Windows" else "utf-8",
            errors="ignore",
        )
        return result.stdout or "", result.returncode

    @staticmethod
    async def ping(host: str, count: int = 4, timeout: int = 2) -> dict:
        """单主机Ping — 逐包发送以获取每次延迟"""
        results = []
        for i in range(count):
            start = time.time()
            try:
                loop = asyncio.get_event_loop()
                stdout, returncode = await loop.run_in_executor(
                    PingTool._executor,
                    PingTool._run_ping_sync,
                    host,
                    1,  # 每次只发1个包
                    timeout,
                )
                elapsed = round((time.time() - start) * 1000, 2)

                if returncode == 0:
                    time_match = re.search(r"(?:time[=<]\s*)([\d.]+)\s*ms", stdout)
                    rtt = float(time_match.group(1)) if time_match else elapsed
                    results.append({"seq": i + 1, "success": True, "rtt": rtt})
                else:
                    results.append({"seq": i + 1, "success": False, "error": "Request timeout"})
            except asyncio.TimeoutError:
                results.append({"seq": i + 1, "success": False, "error": "Timeout"})
            except Exception as e:
                results.append({"seq": i + 1, "success": False, "error": str(e)})

        success_count = sum(1 for r in results if r["success"])
        rtts = [r["rtt"] for r in results if r.get("rtt")]
        return {
            "host": host,
            "count": count,
            "success": success_count,
            "loss": round((count - success_count) / count * 100, 1),
            "min_rtt": round(min(rtts), 2) if rtts else 0,
            "max_rtt": round(max(rtts), 2) if rtts else 0,
            "avg_rtt": round(sum(rtts) / len(rtts), 2) if rtts else 0,
            "results": results,
        }

    @staticmethod
    async def ping_batch(hosts: list[str], count: int = 2) -> list[dict]:
        """批量Ping"""
        tasks = [PingTool.ping(h, count) for h in hosts]
        return await asyncio.gather(*tasks)

    @staticmethod
    async def ping_scan(network: str, timeout: int = 1) -> list[dict]:
        """Ping扫描网段"""
        try:
            import ipaddress

            net = ipaddress.ip_network(network, strict=False)
            hosts = [str(ip) for ip in net.hosts()]
        except ValueError:
            return [{"error": f"无效网段: {network}"}]

        sem = asyncio.Semaphore(50)

        async def scan_one(host: str) -> dict:
            async with sem:
                result = await PingTool.ping(host, count=1, timeout=timeout)
                return {"host": host, "alive": result["success"] > 0}

        tasks = [scan_one(h) for h in hosts[:254]]
        return await asyncio.gather(*tasks)


ping_tool = PingTool()

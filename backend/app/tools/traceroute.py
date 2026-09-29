"""路由跟踪工具"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor


class TraceRoute:
    """Traceroute 路由追踪"""

    # 使用独立线程池，避免 Windows ProactorEventLoop 的 executor 问题
    _executor = ThreadPoolExecutor(max_workers=2)

    @staticmethod
    async def trace(host: str, max_hops: int = 30, timeout: int = 3) -> list[dict]:
        """路由跟踪"""
        is_win = platform.system() == "Windows"

        try:
            if is_win:
                # Windows: tracert 是控制台程序，通过 shell 执行避免 stdout 缓冲阻塞
                loop = asyncio.get_event_loop()
                cmd_str = f'tracert -d -h {max_hops} -w {timeout * 1000} {host}'
                output = await loop.run_in_executor(
                    TraceRoute._executor,
                    lambda: subprocess.run(
                        cmd_str, capture_output=True, text=True,
                        shell=True, timeout=max_hops * timeout + 60,
                        encoding="gbk", errors="ignore",
                    ).stdout or ""
                )
                return TraceRoute._parse_tracert(output, host, max_hops)
            else:
                # Linux/Mac: 使用 traceroute
                loop = asyncio.get_event_loop()
                output = await loop.run_in_executor(
                    TraceRoute._executor,
                    lambda: subprocess.run(
                        ["traceroute", "-n", "-m", str(max_hops),
                         "-w", str(timeout), "-q", "1", host],
                        capture_output=True, text=True,
                        timeout=max_hops * timeout + 30,
                        errors="ignore",
                    ).stdout or ""
                )
                return TraceRoute._parse_traceroute(output, host, max_hops)

        except Exception as e:
            return [{"hop": 1, "ip": "*", "rtt": 0, "reached": False, "error": str(e)}]

    @staticmethod
    def _parse_tracert(output: str, target: str, max_hops: int) -> list[dict]:
        """解析 Windows tracert 输出

        典型输出：
          Tracing route to 8.8.8.8 over a maximum of 30 hops:
            1     1 ms    <1 ms    <1 ms  192.168.1.1
            2     *      *        *     Request timed out.
            3     5 ms    4 ms    5 ms  8.8.8.8
          Trace complete.
        """
        results = []
        lines = output.strip().split("\n")

        for line in lines:
            # 跳过标题行和结尾行
            line = line.strip()
            if not line or "Tracing route" in line or "over a maximum" in line \
                    or "Trace complete" in line or line.startswith("Round trip"):
                continue

            # 匹配数据行: 开头是跳数数字
            m = re.match(r"\s*(\d+)\s+(.*)", line)
            if not m:
                continue

            hop_num = int(m.group(1))
            rest = m.group(2).strip()

            # 提取IP地址（行末尾的IPv4）
            ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*$", rest)
            if ip_match:
                ip = ip_match.group(1)
                # 提取延迟时间（第一个出现的 <数字> ms 或 数字 ms）
                rtt_match = re.search(r"<(\d+)\s*ms|(\d+)\s*ms", rest)
                rtt_str = rtt_match.group(1) or rtt_match.group(2) if rtt_match else None
                rtt = int(rtt_str) if rtt_str else 0
                reached = ip == target
                results.append({"hop": hop_num, "ip": ip, "rtt": rtt, "reached": reached})
                if reached:
                    break
            elif "*" in rest or "Request timed out" in line.lower():
                # 超时行
                results.append({"hop": hop_num, "ip": "*", "rtt": 0, "reached": False})

        # 如果没有解析到任何行，返回一个错误结果
        if not results:
            results.append({"hop": 1, "ip": "*", "rtt": 0, "reached": False, "error": "无法解析 tracert 输出"})

        return results

    @staticmethod
    def _parse_traceroute(output: str, target: str, max_hops: int) -> list[dict]:
        """解析 Linux/Mac traceroute 输出"""
        results = []
        lines = [l.strip() for l in output.split("\n") if l.strip()]

        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    hop_num = int(parts[0])
                except ValueError:
                    continue
                if parts[1] != "*":
                    ip = parts[1]
                    # 尝试提取延迟
                    rtt = 0
                    for p in parts[2:]:
                        rm = re.match(r"([\d.]+)\s*ms", p)
                        if rm:
                            rtt = float(rm.group(1))
                            break
                    reached = target in line or ip == target
                    results.append({"hop": hop_num, "ip": ip, "rtt": round(rtt, 2), "reached": reached})
                    if reached:
                        break
                else:
                    results.append({"hop": hop_num, "ip": "*", "rtt": 0, "reached": False})

        if not results:
            results.append({"hop": 1, "ip": "*", "rtt": 0, "reached": False, "error": "无法解析 traceroute 输出"})

        return results


trace_route = TraceRoute()

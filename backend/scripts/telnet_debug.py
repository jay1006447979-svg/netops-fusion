"""Telnet 调试脚本 — 观察设备真实交互流程"""

import asyncio
import sys

HOST, PORT = "192.168.1.20", 2001


async def main():
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(HOST, PORT), timeout=10
    )
    print(f"[connect] {HOST}:{PORT}")

    async def dump(tag, seconds):
        out = b""
        try:
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=seconds)
                if not chunk:
                    break
                out += chunk
                if len(out) > 8000:
                    break
        except asyncio.TimeoutError:
            pass
        print(f"[{tag}] {len(out)} bytes:")
        print(repr(out.decode(errors="ignore")[:1500]))
        print("-" * 60)
        return out

    await dump("banner", 8)
    writer.write(b"\n")
    await writer.drain()
    await dump("after-newline", 5)
    writer.write(b"display current-configuration\n")
    await writer.drain()
    out = await dump("after-cmd", 15)
    if b"More" in out:
        print(">>> 设备在分页!")
    writer.close()


asyncio.run(main())

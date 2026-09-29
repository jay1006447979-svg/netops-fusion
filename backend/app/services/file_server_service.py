"""内置文件服务 — TFTP / FTP 服务器

用途: 将 backend/data/backups 目录暴露给网络设备, 方便在设备上直接拉取/推送配置文件。
    - TFTP: 纯 asyncio 实现 (RFC 1350), 支持读(RRQ)/写(WRQ, 仅限 uploads/ 目录)
    - FTP : pyftpdlib 实现, 匿名只读, netops/netops 账号可读写
"""

from __future__ import annotations

import asyncio
import datetime
import struct
import threading
from pathlib import Path

from app.services.backup_service import BACKUP_ROOT, ensure_dirs

TFTP_DEFAULT_PORT = 69
FTP_DEFAULT_PORT = 21
FTP_USER = "netops"
FTP_PASS = "netops"
FTP_PASSIVE_PORTS = (50000, 50100)


# ============================================================
# TFTP 服务器 (RFC 1350, octet 模式)
# ============================================================
OP_RRQ, OP_WRQ, OP_DATA, OP_ACK, OP_ERR = 1, 2, 3, 4, 5
_TFTP_ERRORS = {
    0: "Undefined error",
    1: "File not found",
    2: "Access denied",
    3: "Disk full",
    4: "Illegal TFTP operation",
    6: "File already exists",
}


def _err_packet(code: int, msg: str = "") -> bytes:
    return struct.pack("!HH", OP_ERR, code) + msg.encode() + b"\x00"


class _TFTPTransfer(asyncio.DatagramProtocol):
    """单次传输会话 — 独立的临时 UDP 端口"""

    def __init__(self):
        self.transport = None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.closed = False

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.queue.put_nowait(data)

    def error_received(self, exc):
        self.queue.put_nowait(None)


class _TFTPListenProtocol(asyncio.DatagramProtocol):
    """69 端口监听 — 只处理初始 RRQ/WRQ 请求"""

    def __init__(self, server: "TFTPServer"):
        self.server = server

    def connection_made(self, transport):
        self.server._transport = transport

    def datagram_received(self, data, addr):
        if len(data) < 4:
            return
        op = struct.unpack("!H", data[:2])[0]
        if op not in (OP_RRQ, OP_WRQ):
            return
        parts = data[2:].split(b"\x00")
        if len(parts) < 2:
            return
        filename = parts[0].decode(errors="replace").strip().replace("\\", "/")
        mode = parts[1].decode(errors="replace").lower()
        asyncio.get_running_loop().create_task(
            self.server.handle_request(addr, op, filename, mode)
        )


class TFTPServer:
    """TFTP 服务器 — 读任意备份文件, 写仅限 uploads/ 目录"""

    def __init__(self, root: Path, host: str = "0.0.0.0", port: int = TFTP_DEFAULT_PORT):
        self.root = root
        self.host = host
        self.port = port
        self.running = False
        self._transport = None
        self._task = None
        self.transfers_done = 0
        self.last_error = ""
        # 最近 50 笔传输日志 — 排查设备端上传/下载失败的关键依据
        self.transfer_log: list[dict] = []

    def _log_transfer(self, op: str, client: str, filename: str, path: str, ok: bool, detail: str):
        self.transfer_log.append({
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "op": op,
            "client": client,
            "filename": filename,
            "path": path,
            "ok": ok,
            "detail": detail,
        })
        if len(self.transfer_log) > 50:
            self.transfer_log = self.transfer_log[-50:]

    def _safe_path(self, filename: str, for_write: bool = False) -> Path:
        """路径安全校验: 读限根目录内, 写限 uploads/ 内"""
        clean = filename.strip("/").replace("\\", "/")
        if not clean or ".." in clean.split("/"):
            raise ValueError("非法路径")
        if for_write and not clean.startswith("uploads/"):
            clean = "uploads/" + clean
        target = (self.root / clean).resolve()
        root_resolved = self.root.resolve()
        if root_resolved not in target.parents and target != root_resolved:
            raise ValueError("路径越界")
        if for_write:
            uploads = (root_resolved / "uploads").resolve()
            if target.parent != uploads:
                raise ValueError("写入仅允许 uploads/ 目录")
        return target

    def _resolve_read_path(self, filename: str) -> Path:
        """解析读取路径 — 设备友好: 纯文件名时自动在子目录中递归查找

        备份文件按 backups/<设备名>/<文件>.cfg 分目录存放, 但设备端 tftp get
        通常只给文件名 (不知道服务端目录结构)。规则:
        1. 先按根目录相对路径找 (支持 <设备名>/<文件名>)
        2. 纯文件名在根下不存在时, 递归搜索所有子目录:
           - 唯一命中 → 直接使用
           - 多个命中 → 取最近修改的 (通常是最新备份)
        """
        target = self._safe_path(filename)
        if target.exists():
            return target
        if "/" not in filename:
            matches = [p for p in self.root.rglob(filename) if p.is_file()]
            if matches:
                matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                return matches[0]
        return target  # 保持原行为, 由上层报 File not found

    async def start(self) -> dict:
        if self.running:
            return {"success": True, "message": f"TFTP 已在运行 (端口 {self.port})"}
        ensure_dirs()
        loop = asyncio.get_running_loop()
        # 重试 3 次 — 停止后立即重启时旧套接字可能尚未完全释放
        last_exc: OSError | None = None
        for _ in range(3):
            try:
                self._transport, _ = await loop.create_datagram_endpoint(
                    lambda: _TFTPListenProtocol(self),
                    local_addr=(self.host, self.port),
                )
                break
            except OSError as e:
                last_exc = e
                await asyncio.sleep(0.8)
        else:
            self.running = False
            msg = str(last_exc)
            if "10048" in msg:
                msg = (
                    f"端口 {self.port} 被占用 — 可能是其他 TFTP 程序 (如 Tftpd64) 正在运行, "
                    f"请先关闭它; 或上一次停止尚未完成, 稍等几秒再试; 也可以改用其他端口"
                )
            return {"success": False, "message": f"TFTP 启动失败: {msg}"}
        self.running = True
        self.last_error = ""
        return {"success": True, "message": f"TFTP 已启动: {self.host}:{self.port}, 根目录 {self.root}"}

    def stop(self) -> dict:
        if not self.running:
            return {"success": True, "message": "TFTP 未在运行"}
        if self._transport:
            self._transport.close()
            self._transport = None
        self.running = False
        return {"success": True, "message": "TFTP 已停止"}

    async def handle_request(self, addr, op: int, filename: str, mode: str):
        # Windows Proactor 下 datagram_received 的 addr 可能是 4 元组
        # (IPv4-mapped IPv6 形式), sendto 需要规范化为 2 元组
        if isinstance(addr, tuple) and len(addr) > 2:
            addr = (addr[0], addr[1])
        try:
            if op == OP_RRQ:
                await self._handle_read(addr, filename)
            else:
                await self._handle_write(addr, filename)
        except Exception as e:  # 传输层兜底
            self.last_error = f"{filename}: {e}"
        self.transfers_done += 1

    def _new_transfer(self) -> tuple[asyncio.DatagramTransport, _TFTPTransfer, asyncio.Task]:
        raise NotImplementedError

    async def _handle_read(self, addr, filename: str):
        client = f"{addr[0]}:{addr[1]}"
        loop = asyncio.get_running_loop()
        proto = _TFTPTransfer()
        # 显式绑定 IPv4 随机端口: 不指定 local_addr 时 asyncio 可能创建 IPv6 族
        # 套接字, 导致向 IPv4 地址 sendto 报 "unexpected address family"
        transport, _ = await loop.create_datagram_endpoint(
            lambda: proto, local_addr=("0.0.0.0", 0)
        )
        try:
            try:
                path = self._resolve_read_path(filename)
                data = path.read_bytes()
            except FileNotFoundError:
                self.last_error = f"{filename}: File not found (已尝试子目录递归查找)"
                self._log_transfer("读", client, filename, "-", False,
                                   "文件不存在 (已递归查找子目录) — 设备端会生成空文件")
                transport.sendto(_err_packet(1, "File not found"), addr)
                return
            except (ValueError, PermissionError) as e:
                self._log_transfer("读", client, filename, "-", False, f"路径被拒绝: {e}")
                transport.sendto(_err_packet(2, str(e)), addr)
                return
            except IsADirectoryError:
                self._log_transfer("读", client, filename, "-", False, "是目录不是文件")
                transport.sendto(_err_packet(1, "Is a directory"), addr)
                return

            block = 0
            while True:
                block = (block % 65535) + 1
                chunk = data[(block - 1) * 512: block * 512]
                pkt = struct.pack("!HH", OP_DATA, block) + chunk
                acked = False
                for _ in range(5):  # 最多重传 5 次
                    transport.sendto(pkt, addr)
                    try:
                        reply = await asyncio.wait_for(proto.queue.get(), timeout=3)
                    except asyncio.TimeoutError:
                        continue
                    if reply is None:
                        return
                    if len(reply) >= 4 and struct.unpack("!HH", reply[:4]) == (OP_ACK, block):
                        acked = True
                        break
                if not acked:
                    self.last_error = f"{filename}: 对端无响应"
                    self._log_transfer("读", client, filename, str(path), False,
                                       "对端无响应 (重传耗尽)")
                    return
                if len(chunk) < 512:
                    break
            self._log_transfer("读", client, filename, str(path), True,
                               f"传输完成, 共 {len(data)} 字节")
        finally:
            transport.close()

    async def _handle_write(self, addr, filename: str):
        client = f"{addr[0]}:{addr[1]}"
        loop = asyncio.get_running_loop()
        proto = _TFTPTransfer()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: proto, local_addr=("0.0.0.0", 0)
        )
        try:
            try:
                path = self._safe_path(filename, for_write=True)
            except (ValueError, PermissionError) as e:
                self._log_transfer("写", client, filename, "-", False, f"路径被拒绝: {e}")
                transport.sendto(_err_packet(2, str(e)), addr)
                return
            if path.exists():
                self._log_transfer("写", client, filename, str(path), False, "文件已存在")
                transport.sendto(_err_packet(6, "File already exists"), addr)
                return
            path.parent.mkdir(parents=True, exist_ok=True)

            transport.sendto(struct.pack("!HH", OP_ACK, 0), addr)  # ACK 写请求
            chunks = {}
            expected = 1
            while True:
                try:
                    reply = await asyncio.wait_for(proto.queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    self.last_error = f"{filename}: 写入超时"
                    self._log_transfer("写", client, filename, str(path), False, "接收超时")
                    return
                if reply is None or len(reply) < 4:
                    return
                op, block = struct.unpack("!HH", reply[:4])
                if op != OP_DATA or block != expected:
                    continue
                chunks[block] = reply[4:]
                transport.sendto(struct.pack("!HH", OP_ACK, block), addr)
                if len(reply[4:]) < 512:
                    break
                expected = (expected % 65535) + 1

            payload = b"".join(chunks[k] for k in sorted(chunks))
            path.write_bytes(payload)
            self._log_transfer("写", client, filename, str(path), True,
                               f"接收完成, 共 {len(payload)} 字节")
        finally:
            transport.close()


# ============================================================
# FTP 服务器 (pyftpdlib, 独立线程)
# ============================================================
class FTPServer:
    def __init__(self, root: Path, host: str = "0.0.0.0", port: int = FTP_DEFAULT_PORT):
        self.root = root
        self.host = host
        self.port = port
        self.running = False
        self._server = None
        self._thread = None
        self._stop_event = threading.Event()

    def start(self) -> dict:
        if self.running:
            return {"success": True, "message": f"FTP 已在运行 (端口 {self.port})"}
        try:
            from pyftpdlib.authorizers import DummyAuthorizer
            from pyftpdlib.handlers import FTPHandler
            from pyftpdlib.servers import FTPServer
        except ImportError:
            return {"success": False, "message": "缺少 pyftpdlib, 无法启动 FTP"}

        ensure_dirs()
        auth = DummyAuthorizer()
        # 匿名只读 (设备用 anonymous 拉配置)
        auth.add_anonymous(str(self.root), perm="elr")
        # netops 账号可读写 (设备可 put 配置到 uploads/)
        auth.add_user(FTP_USER, FTP_PASS, str(self.root), perm="elradfmw")

        handler = FTPHandler
        handler.authorizer = auth
        handler.banner = "NetOps Fusion backup FTP"
        handler.passive_ports = range(FTP_PASSIVE_PORTS[0], FTP_PASSIVE_PORTS[1])

        try:
            self._server = FTPServer((self.host, self.port), handler)
        except OSError as e:
            return {"success": False, "message": f"FTP 启动失败: {e}"}

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        self.running = True
        return {
            "success": True,
            "message": f"FTP 已启动: {self.host}:{self.port} (匿名只读 / {FTP_USER} 可读写)",
        }

    def _serve(self):
        try:
            while not self._stop_event.is_set():
                self._server.serve_forever(timeout=0.5, blocking=False)
        except Exception:
            pass

    def stop(self) -> dict:
        if not self.running:
            return {"success": True, "message": "FTP 未在运行"}
        self._stop_event.set()
        try:
            self._server.close_all()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=3)
        self._server = None
        self.running = False
        return {"success": True, "message": "FTP 已停止"}


# ============================================================
# 全局单例
# ============================================================
tftp_server = TFTPServer(BACKUP_ROOT)
ftp_server = FTPServer(BACKUP_ROOT)

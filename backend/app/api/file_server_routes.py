"""文件服务 API — 内置 TFTP / FTP 服务器的启停与状态"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.file_server_service import (
    FTP_DEFAULT_PORT,
    FTP_PASSIVE_PORTS,
    FTP_USER,
    TFTP_DEFAULT_PORT,
    ftp_server,
    tftp_server,
)
from app.services.backup_service import BACKUP_ROOT

router = APIRouter(prefix="/api/fileservers", tags=["文件服务(TFTP/FTP)"])


class PortRequest(BaseModel):
    port: int | None = None


def _status() -> dict:
    return {
        "root": str(BACKUP_ROOT),
        "tftp": {
            "running": tftp_server.running,
            "host": tftp_server.host,
            "port": tftp_server.port,
            "default_port": TFTP_DEFAULT_PORT,
            "transfers_done": tftp_server.transfers_done,
            "last_error": tftp_server.last_error,
            "transfer_log": list(reversed(tftp_server.transfer_log)),
        },
        "ftp": {
            "running": ftp_server.running,
            "host": ftp_server.host,
            "port": ftp_server.port,
            "default_port": FTP_DEFAULT_PORT,
            "passive_ports": list(FTP_PASSIVE_PORTS),
            "user": FTP_USER,
        },
    }


@router.get("/status")
async def status():
    """获取 TFTP/FTP 服务器状态"""
    return {"success": True, **_status()}


@router.post("/tftp/start")
async def start_tftp(req: PortRequest):
    """启动 TFTP 服务器"""
    if req.port:
        tftp_server.port = req.port
    r = await tftp_server.start()
    return {"success": r["success"], "message": r["message"], **_status()}


@router.post("/tftp/stop")
async def stop_tftp():
    """停止 TFTP 服务器"""
    r = tftp_server.stop()
    return {"success": r["success"], "message": r["message"], **_status()}


@router.post("/ftp/start")
async def start_ftp(req: PortRequest):
    """启动 FTP 服务器"""
    if req.port:
        ftp_server.port = req.port
    r = ftp_server.start()
    return {"success": r["success"], "message": r["message"], **_status()}


@router.post("/ftp/stop")
async def stop_ftp():
    """停止 FTP 服务器"""
    r = ftp_server.stop()
    return {"success": r["success"], "message": r["message"], **_status()}

"""配置备份服务 — 设备配置落盘为 .cfg 文件 + 数据库索引

目录结构:
    backend/data/backups/
        <设备名>/
            <设备名>_<YYYYmmdd_HHMMSS>.cfg
        uploads/          # TFTP/FTP 允许写入的目录
"""

from __future__ import annotations

import asyncio
import datetime
import re
from pathlib import Path

from app.db.base import get_session
from app.db.models import Device, DeviceConfig as DeviceConfigModel, AuditLog
from app.services.device_connector import (
    get_connector,
    ConnectionParams,
    ConnectionType,
)

# 备份根目录: backend/data/backups
BACKUP_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "backups"

# 批量/自动备份时的并发保护
_backup_lock = asyncio.Lock()

# 后台任务引用集 (防止任务被 GC)
_bg_tasks: set[asyncio.Task] = set()


def sanitize_device_name(name: str) -> str:
    """设备名转为安全的目录/文件名片段"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t ]+', "_", (name or "device").strip())
    return cleaned[:64] or "device"


def resolve_backup_file(rel_path: str | None) -> Path | None:
    """将数据库中的相对路径解析为备份根目录下的绝对路径 (防越界)。

    Args:
        rel_path: 数据库 file_path 字段, 如 "SW-Telnet/SW-Telnet_20260914.cfg"
    Returns:
        安全的绝对 Path; 路径非法或越界时返回 None
    """
    if not rel_path:
        return None
    try:
        full = (BACKUP_ROOT / rel_path).resolve()
        full.relative_to(BACKUP_ROOT.resolve())
    except (ValueError, OSError):
        return None
    return full


def backup_file_exists(rel_path: str | None) -> bool:
    """检测 .cfg 文件是否真实存在于磁盘"""
    full = resolve_backup_file(rel_path)
    return bool(full and full.is_file())


def delete_backup_file(rel_path: str | None) -> dict:
    """删除磁盘上的 .cfg 文件 (记录删除时同步调用)

    Returns:
        {deleted: bool, path: str|None, message: str}
    """
    full = resolve_backup_file(rel_path)
    if not full:
        return {"deleted": False, "path": rel_path, "message": "路径非法或为空, 跳过文件删除"}
    if not full.is_file():
        return {"deleted": False, "path": str(full), "message": "文件不存在 (可能已被手动删除)"}
    try:
        full.unlink()
        return {"deleted": True, "path": str(full), "message": f"已删除文件: {full.name}"}
    except OSError as e:
        return {"deleted": False, "path": str(full), "message": f"删除文件失败: {e}"}


def restore_backup_file(rel_path: str | None, content: str) -> dict:
    """根据数据库中的配置内容恢复 .cfg 文件 (文件丢失时使用)

    Returns:
        {restored: bool, path: str|None, size: int, message: str}
    """
    full = resolve_backup_file(rel_path)
    if not full:
        return {"restored": False, "path": rel_path, "size": 0, "message": "路径非法或为空, 无法恢复"}
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content or "", encoding="utf-8")
        size = len(content or "")
        return {"restored": True, "path": str(full), "size": size, "message": f"文件已恢复: {full.name} ({size} 字符)"}
    except OSError as e:
        return {"restored": False, "path": str(full), "size": 0, "message": f"恢复文件失败: {e}"}


def ensure_dirs() -> None:
    (BACKUP_ROOT / "uploads").mkdir(parents=True, exist_ok=True)


async def backup_device(device_id: str, trigger: str = "manual") -> dict:
    """备份单台设备: 连接 → 抓取运行配置 → 写 .cfg 文件 → 写数据库索引

    Args:
        device_id: 设备 ID
        trigger: 触发方式 (manual / auto_add / batch)
    Returns:
        {success, message, file?, version_label?, device_name?}
    """
    async with _backup_lock:
        async with get_session() as session:
            device = await session.get(Device, device_id)
            if not device:
                return {"success": False, "message": "设备不存在", "device_id": device_id}
            device_name = device.name
            vendor = device.vendor
            host = device.host
            if not host:
                return {
                    "success": False,
                    "message": "设备未配置管理地址, 无法备份",
                    "device_id": device_id,
                    "device_name": device_name,
                }
            connection_type = device.connection_type or "ssh"
            port = device.port or (
                22 if connection_type != "telnet" else 23
            )
            username = device.username
            password = device.password

        params = ConnectionParams(
            connection_type=ConnectionType(connection_type),
            host=host,
            port=port,
            username=username,
            password=password,
            vendor=vendor,
        )
        connector = get_connector()
        conn_result = await connector.connect(params)
        if not conn_result.success:
            return {
                "success": False,
                "message": f"连接失败: {conn_result.message}",
                "device_id": device_id,
                "device_name": device_name,
            }

        try:
            cfg_result = await connector.get_running_config(vendor)
        finally:
            await connector.disconnect()

        if not cfg_result.success:
            return {
                "success": False,
                "message": f"获取配置失败: {cfg_result.message}",
                "device_id": device_id,
                "device_name": device_name,
            }

        # ---- 写 .cfg 文件 ----
        ensure_dirs()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = sanitize_device_name(device_name)
        filename = f"{safe_name}_{ts}.cfg"
        rel_dir = BACKUP_ROOT / safe_name
        rel_dir.mkdir(parents=True, exist_ok=True)
        file_full = rel_dir / filename
        rel_path = f"{safe_name}/{filename}".replace("\\", "/")
        file_full.write_text(cfg_result.output, encoding="utf-8")

        # ---- 写数据库索引 ----
        version_label = f"backup-{ts}"
        async with get_session() as session:
            session.add(
                DeviceConfigModel(
                    device_id=device_id,
                    config_text=cfg_result.output,
                    version_label=version_label,
                    file_path=rel_path,
                    source="backup",
                    pushed_by=trigger,
                )
            )
            session.add(
                AuditLog(
                    action="backup_config",
                    target=device_name,
                    operator="system",
                    status="success",
                    detail={
                        "device_id": device_id,
                        "trigger": trigger,
                        "file_path": rel_path,
                        "size": len(cfg_result.output),
                    },
                )
            )

        return {
            "success": True,
            "message": f"备份成功: {rel_path} ({len(cfg_result.output)} 字符)",
            "device_id": device_id,
            "device_name": device_name,
            "file": rel_path,
            "version_label": version_label,
            "size": len(cfg_result.output),
        }


async def backup_all_devices() -> dict:
    """批量备份所有设备 — 串行执行 (连接器为全局单例, 不能并发)"""
    async with get_session() as session:
        result = await session.execute(
            Device.__table__.select().order_by(Device.created_at)
        )
        devices = [dict(r._mapping) for r in result.fetchall()]

    results = []
    for d in devices:
        r = await backup_device(d["id"], trigger="batch")
        results.append(r)

    ok = sum(1 for r in results if r["success"])
    return {
        "success": True,
        "total": len(results),
        "ok": ok,
        "failed": len(results) - ok,
        "results": results,
    }


def schedule_background_backup(device_id: str, trigger: str = "auto_add") -> None:
    """添加设备后自动触发一次备份 (后台执行, 不阻塞请求)"""
    task = asyncio.get_running_loop().create_task(backup_device(device_id, trigger))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)

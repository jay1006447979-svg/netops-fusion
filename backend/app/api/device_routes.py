"""设备管理 API — 设备CRUD + 连接 + 配置推送 + 配置备份"""

from __future__ import annotations

import datetime
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.db.base import get_session
from app.db.models import Device, DeviceConfig as DeviceConfigModel, AuditLog
from app.services.device_connector import (
    get_connector,
    tcp_probe,
    ConnectionParams,
    ConnectionType,
)
from app.services.backup_service import (
    backup_device,
    backup_all_devices,
    schedule_background_backup,
    backup_file_exists,
    delete_backup_file,
    restore_backup_file,
)

router = APIRouter(prefix="/api/devices", tags=["设备管理"])


class DeviceCreate(BaseModel):
    name: str
    vendor: str
    device_type: str = "switch"
    connection_type: str = "ssh"
    host: str | None = None
    port: int = 22
    username: str | None = None
    password: str | None = None
    enable_password: str | None = None
    location: str | None = None
    remark: str | None = None


class DeviceUpdate(BaseModel):
    name: str | None = None
    vendor: str | None = None
    device_type: str | None = None
    connection_type: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    location: str | None = None
    remark: str | None = None


class PushConfigRequest(BaseModel):
    config_text: str
    vendor: str = "huawei"


@router.get("")
async def list_devices():
    """获取设备列表"""
    async with get_session() as session:
        result = await session.execute(select(Device).order_by(Device.created_at.desc()))
        devices = result.scalars().all()
        return {
            "success": True,
            "devices": [
                {
                    "id": d.id,
                    "name": d.name,
                    "vendor": d.vendor,
                    "device_type": d.device_type,
                    "connection_type": d.connection_type,
                    "host": d.host,
                    "port": d.port,
                    "location": d.location,
                    "remark": d.remark,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in devices
            ],
        }


@router.post("")
async def create_device(req: DeviceCreate):
    """添加设备 — 成功后自动在后台触发一次配置备份"""
    async with get_session() as session:
        device = Device(
            name=req.name,
            vendor=req.vendor,
            device_type=req.device_type,
            connection_type=req.connection_type,
            host=req.host,
            port=req.port,
            username=req.username,
            password=req.password,
            enable_password=req.enable_password,
            location=req.location,
            remark=req.remark,
        )
        session.add(device)
        await session.flush()
        device_id = device.id

    auto_backup_started = False
    if req.host:
        try:
            schedule_background_backup(device_id, trigger="auto_add")
            auto_backup_started = True
        except Exception:
            pass
    return {
        "success": True,
        "device_id": device_id,
        "auto_backup_started": auto_backup_started,
        "message": "设备已添加, 正在后台自动备份配置" if auto_backup_started else "设备已添加 (未配置管理地址, 跳过自动备份)",
    }


@router.post("/backup-all")
async def backup_all():
    """批量备份所有设备 — 串行执行, 返回逐台结果"""
    return await backup_all_devices()


@router.put("/{device_id}")
async def update_device(device_id: str, req: DeviceUpdate):
    """更新设备"""
    async with get_session() as session:
        device = await session.get(Device, device_id)
        if not device:
            raise HTTPException(404, "设备不存在")
        for k, v in req.model_dump(exclude_unset=True).items():
            setattr(device, k, v)
        return {"success": True}


@router.delete("/{device_id}")
async def delete_device(device_id: str):
    """删除设备"""
    async with get_session() as session:
        device = await session.get(Device, device_id)
        if not device:
            raise HTTPException(404, "设备不存在")
        await session.delete(device)
        return {"success": True}


@router.post("/{device_id}/test")
async def test_connection(device_id: str):
    """测试设备连通性 — 两级检测: TCP 快速探测(3s) + 完整登录验证(8s), 返回耗时明细"""
    async with get_session() as session:
        device = await session.get(Device, device_id)
        if not device:
            raise HTTPException(404, "设备不存在")

    port = device.port or (22 if (device.connection_type or "ssh") != "telnet" else 23)
    t0 = time.perf_counter()
    checks: dict = {}

    # 第一级: TCP 快速探测 — 网络不通 3 秒内直接失败, 不走完整登录
    tcp_ok, tcp_msg = await tcp_probe(device.host, port, timeout=3.0)
    tcp_ms = int((time.perf_counter() - t0) * 1000)
    checks["tcp"] = {"ok": tcp_ok, "message": tcp_msg, "elapsed_ms": tcp_ms}
    if not tcp_ok:
        return {
            "success": False,
            "status": "error",
            "message": tcp_msg,
            "elapsed_ms": tcp_ms,
            "checks": checks,
        }

    # 第二级: 完整登录验证 (连接超时降为 8s)
    params = ConnectionParams(
        connection_type=ConnectionType(device.connection_type or "ssh"),
        host=device.host,
        port=port,
        username=device.username,
        password=device.password,
        timeout=8,
    )
    connector = get_connector()
    result = await connector.test_connection(params)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    checks["login"] = {
        "ok": result.success,
        "message": result.message,
        "elapsed_ms": elapsed_ms,
    }
    return {
        "success": result.success,
        "status": result.status.value,
        "message": result.message,
        "elapsed_ms": elapsed_ms,
        "checks": checks,
    }


@router.post("/{device_id}/push")
async def push_config(device_id: str, req: PushConfigRequest):
    """推送配置到设备 — 带命令级回滚"""
    async with get_session() as session:
        device = await session.get(Device, device_id)
        if not device:
            raise HTTPException(404, "设备不存在")

    params = ConnectionParams(
        connection_type=ConnectionType(device.connection_type or "ssh"),
        host=device.host,
        port=device.port or (22 if (device.connection_type or "ssh") != "telnet" else 23),
        username=device.username,
        password=device.password,
        vendor=req.vendor,
    )

    connector = get_connector()
    conn_result = await connector.connect(params)

    if not conn_result.success:
        return {
            "success": False,
            "message": conn_result.message,
        }

    push_result = await connector.send_config(req.config_text, req.vendor)

    # 记录审计日志
    async with get_session() as session:
        log = AuditLog(
            action="push_config",
            target=device.name,
            operator="system",
            status="success" if push_result.success else "failed",
            detail={
                "device_id": device_id,
                "rollback_performed": push_result.rollback_performed,
                "commands_executed": len(push_result.results),
                "commands_rolled_back": len(push_result.rollback_results),
            },
        )
        session.add(log)

        # 保存配置版本
        if push_result.success:
            cfg = DeviceConfigModel(
                device_id=device_id,
                config_text=req.config_text,
                source="push",
                pushed_by="system",
            )
            session.add(cfg)

    await connector.disconnect()

    return {
        "success": push_result.success,
        "message": push_result.message,
        "rollback_performed": push_result.rollback_performed,
        "commands_total": len(push_result.results),
        "commands_success": sum(1 for r in push_result.results if r.success),
        "rollback_commands": len(push_result.rollback_results),
        "output": push_result.output,
    }


@router.get("/{device_id}/configs")
async def list_device_configs(device_id: str):
    """获取设备配置历史"""
    async with get_session() as session:
        result = await session.execute(
            select(DeviceConfigModel)
            .where(DeviceConfigModel.device_id == device_id)
            .order_by(DeviceConfigModel.created_at.desc())
        )
        configs = result.scalars().all()
        return {
            "success": True,
            "configs": [
                {
                    "id": c.id,
                    "version_label": c.version_label,
                    "source": c.source,
                    "pushed_by": c.pushed_by,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "config_text": c.config_text,
                }
                for c in configs
            ],
        }


@router.post("/{device_id}/backup")
async def backup_device_config(device_id: str):
    """备份设备当前运行配置 — 落盘为 .cfg 文件并写数据库索引"""
    return await backup_device(device_id, trigger="manual")


@router.get("/{device_id}/backups")
async def list_device_backups(device_id: str):
    """获取设备配置备份历史 (仅 source=backup)"""
    async with get_session() as session:
        device = await session.get(Device, device_id)
        if not device:
            raise HTTPException(404, "设备不存在")

        result = await session.execute(
            select(DeviceConfigModel)
            .where(
                DeviceConfigModel.device_id == device_id,
                DeviceConfigModel.source == "backup",
            )
            .order_by(DeviceConfigModel.created_at.desc())
        )
        configs = result.scalars().all()
        return {
            "success": True,
            "backups": [
                {
                    "id": c.id,
                    "version_label": c.version_label or "backup",
                    "file_path": c.file_path,
                    "file_exists": backup_file_exists(c.file_path),
                    "size": len(c.config_text or ""),
                    "lines": len((c.config_text or "").splitlines()),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in configs
            ],
        }


@router.get("/{device_id}/backups/{config_id}")
async def get_device_backup(device_id: str, config_id: str):
    """获取单个备份的完整配置内容"""
    async with get_session() as session:
        device = await session.get(Device, device_id)
        if not device:
            raise HTTPException(404, "设备不存在")

        result = await session.execute(
            select(DeviceConfigModel).where(
                DeviceConfigModel.id == config_id,
                DeviceConfigModel.device_id == device_id,
                DeviceConfigModel.source == "backup",
            )
        )
        cfg = result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(404, "备份不存在")
        return {
            "success": True,
            "backup": {
                "id": cfg.id,
                "version_label": cfg.version_label or "backup",
                "config_text": cfg.config_text,
                "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
            },
        }


@router.delete("/{device_id}/backups/{config_id}")
async def delete_device_backup(device_id: str, config_id: str):
    """删除一条配置备份"""
    async with get_session() as session:
        device = await session.get(Device, device_id)
        if not device:
            raise HTTPException(404, "设备不存在")

        result = await session.execute(
            select(DeviceConfigModel).where(
                DeviceConfigModel.id == config_id,
                DeviceConfigModel.device_id == device_id,
                DeviceConfigModel.source == "backup",
            )
        )
        cfg = result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(404, "备份不存在")
        file_path = cfg.file_path
        await session.delete(cfg)
        # 删除记录的同时删除磁盘上的 .cfg 文件
        file_result = delete_backup_file(file_path)
        return {
            "success": True,
            "file_deleted": file_result["deleted"],
            "file_message": file_result["message"],
        }


@router.delete("/{device_id}/backups/{config_id}/file")
async def delete_device_backup_file(device_id: str, config_id: str):
    """仅删除备份对应的 .cfg 文件 (保留数据库记录, 记录将标记为文件缺失)"""
    async with get_session() as session:
        result = await session.execute(
            select(DeviceConfigModel).where(
                DeviceConfigModel.id == config_id,
                DeviceConfigModel.device_id == device_id,
                DeviceConfigModel.source == "backup",
            )
        )
        cfg = result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(404, "备份不存在")
    fr = delete_backup_file(cfg.file_path)
    return {"success": True, **fr}


@router.post("/{device_id}/backups/{config_id}/restore-file")
async def restore_device_backup_file(device_id: str, config_id: str):
    """从数据库配置内容恢复 .cfg 文件 (文件被手动删除后用于找回)"""
    async with get_session() as session:
        result = await session.execute(
            select(DeviceConfigModel).where(
                DeviceConfigModel.id == config_id,
                DeviceConfigModel.device_id == device_id,
                DeviceConfigModel.source == "backup",
            )
        )
        cfg = result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(404, "备份不存在")
    if backup_file_exists(cfg.file_path):
        return {"success": True, "restored": True, "message": "文件已存在, 无需恢复", "path": cfg.file_path}
    rr = restore_backup_file(cfg.file_path, cfg.config_text or "")
    return {"success": rr["restored"], **rr}

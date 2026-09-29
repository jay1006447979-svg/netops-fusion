"""配置生成 API"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.core.http_util import attachment_header
from app.models.device import DeviceConfig
from app.services.config_generator import config_service
from app.services.config_validator import validator

router = APIRouter(prefix="/api/config", tags=["配置生成"])


@router.post("/generate")
async def generate_config(config: DeviceConfig):
    """生成设备配置"""
    result = config_service.generate(config)
    return {"success": True, **result}


@router.post("/validate")
async def validate_config(config: dict):
    """校验配置参数"""
    result = validator.validate(config)
    return {"success": True, **result}


@router.post("/export")
async def export_config(config: DeviceConfig):
    """导出配置文件"""
    result = config_service.generate(config)
    vendor = result["vendor"]
    hostname = result.get("hostname") or "device"
    filename = f"{hostname}_{vendor}.cfg"
    return Response(
        result["config_text"],
        media_type="text/plain",
        headers={
            "Content-Disposition": attachment_header(filename),
            "Content-Type": "text/plain; charset=utf-8",
        },
    )

"""厂商信息 API"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.config_generator import config_service

router = APIRouter(prefix="/api/vendors", tags=["厂商"])


@router.get("")
async def list_vendors():
    """获取支持的厂商列表"""
    return {"success": True, "vendors": config_service.list_vendors()}


@router.get("/{vendor}")
async def get_vendor_detail(vendor: str):
    """获取指定厂商详情"""
    for v in config_service.list_vendors():
        if v["vendor"] == vendor:
            return {"success": True, "vendor": v}
    return {"success": False, "error": f"不支持的厂商: {vendor}"}

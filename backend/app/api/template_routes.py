"""模板 API"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.template_service import template_service

router = APIRouter(prefix="/api/templates", tags=["配置模板"])


@router.get("")
async def list_templates(vendor: str = Query(None)):
    """获取配置模板列表"""
    return {"success": True, "templates": template_service.list_templates(vendor)}


@router.get("/{template_id}")
async def get_template(template_id: str):
    """获取模板详情"""
    data = template_service.get_template(template_id)
    if data is None:
        return {"success": False, "error": f"模板不存在: {template_id}"}
    return {"success": True, "template": data}


@router.get("/{template_id}/config")
async def get_template_config(template_id: str):
    """获取模板配置数据"""
    config = template_service.get_template_config(template_id)
    if config is None:
        return {"success": False, "error": f"模板不存在: {template_id}"}
    return {"success": True, "config": config}

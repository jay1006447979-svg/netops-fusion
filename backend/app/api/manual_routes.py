"""命令手册 API"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.manual_service import manual_service

router = APIRouter(prefix="/api/manual", tags=["命令手册"])


@router.get("/vendors")
async def list_manual_vendors():
    """获取有手册的厂商列表"""
    return {"success": True, "vendors": manual_service.list_vendors()}


@router.get("/stats")
async def manual_stats():
    """获取手册统计信息"""
    return {"success": True, "stats": manual_service.get_stats()}


@router.get("/{vendor}/categories")
async def get_categories(vendor: str):
    """获取厂商命令分类"""
    return {"success": True, "categories": manual_service.get_categories(vendor)}


@router.get("/{vendor}/commands")
async def get_all_commands(vendor: str):
    """获取厂商全部命令"""
    return {"success": True, "commands": manual_service.get_all_commands(vendor)}


@router.get("/{vendor}/category/{category}")
async def get_by_category(vendor: str, category: str):
    """按分类获取命令"""
    return {"success": True, "commands": manual_service.get_by_category(vendor, category)}


@router.get("/{vendor}/cases")
async def get_cases(vendor: str):
    """获取厂商配置案例"""
    return {"success": True, "cases": manual_service.get_cases(vendor)}


@router.get("/search")
async def search_commands(
    keyword: str = Query(..., description="搜索关键词"),
    vendor: str = Query(None, description="厂商过滤"),
):
    """全文检索命令"""
    return {"success": True, "results": manual_service.search(keyword, vendor)}

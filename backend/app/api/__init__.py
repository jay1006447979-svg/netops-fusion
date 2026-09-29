"""API 路由层 — 导出所有路由"""
from app.api.config_routes import router as config_router
from app.api.vendor_routes import router as vendor_router
from app.api.template_routes import router as template_router
from app.api.tool_routes import router as tool_router
from app.api.manual_routes import router as manual_router
from app.api.device_routes import router as device_router
from app.api.note_routes import router as note_router
from app.api.file_server_routes import router as file_server_router
from app.api.topology_routes import router as topology_router
from app.api.ws_routes import router as ws_router

__all__ = [
    "config_router",
    "vendor_router",
    "template_router",
    "tool_router",
    "manual_router",
    "device_router",
    "note_router",
    "file_server_router",
    "topology_router",
    "ws_router",
]

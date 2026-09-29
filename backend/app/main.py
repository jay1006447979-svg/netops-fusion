"""NetOps Fusion — 主程序入口"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings
from app.core.registry import vendor_registry
from app.db.base import init_db
# 导入厂商生成器以触发注册
import app.vendors  # noqa: F401
from app.api import (
    config_router,
    vendor_router,
    template_router,
    tool_router,
    manual_router,
    device_router,
    note_router,
    file_server_router,
    topology_router,
    ws_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    print("=" * 60)
    print(f"  {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"  Network Device Configuration Tool")
    print("=" * 60)
    print(f"  访问地址: http://localhost:{settings.PORT}")
    print(f"  API文档: http://localhost:{settings.PORT}/docs")
    print(f"  调试模式: {'开启' if settings.DEBUG else '关闭'}")
    print(f"  已注册厂商: {vendor_registry.list_vendors()}")
    print("=" * 60)

    await init_db()
    yield
    print("应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="融合版网络设备配置工具 — 多厂商配置生成 + 设备推送(命令级回滚) + 11+网络工具 + 命令手册",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(config_router)
app.include_router(vendor_router)
app.include_router(template_router)
app.include_router(tool_router)
app.include_router(manual_router)
app.include_router(device_router)
app.include_router(note_router)
app.include_router(file_server_router)
app.include_router(topology_router)
app.include_router(ws_router)

# 挂载静态前端资源
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/api/info", tags=["首页"])
async def api_info():
    """系统信息（原根路径 JSON）"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "vendors": vendor_registry.list_vendors(),
        "docs": "/docs",
        "endpoints": {
            "配置生成": "/api/config/generate",
            "厂商列表": "/api/vendors",
            "配置模板": "/api/templates",
            "网络工具": "/api/tools",
            "命令手册": "/api/manual",
            "设备管理": "/api/devices",
            "笔记": "/api/notes",
            "文件服务": "/api/fileservers",
            "拓扑图": "/api/topologies",
            "WebSocket": "/ws/logs",
        },
    }


@app.get("/", tags=["首页"], include_in_schema=False)
async def root(request: Request):
    """根路径 — 返回可视化前端界面"""
    index_file = _STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file), media_type="text/html")
    # 静态目录不存在时回退到 JSON
    return await api_info()


@app.get("/health", tags=["健康检查"])
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

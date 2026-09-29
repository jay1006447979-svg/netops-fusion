"""WebSocket 路由 — 实时日志推送"""

from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.device_connector import get_connector, ConnectionParams, ConnectionType

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """WebSocket 连接管理"""

    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, msg: dict):
        for ws in self.active:
            try:
                await ws.send_json(msg)
            except Exception:
                pass


manager = ConnectionManager()


@router.websocket("/ws/logs")
async def ws_logs(ws: WebSocket):
    """实时日志推送 — 连接后可查看设备连接器日志"""
    await manager.connect(ws)
    connector = get_connector()
    try:
        # 先发送当前已有日志
        await ws.send_json({"type": "init", "logs": connector.log[-50:]})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)

"""拓扑图 API — 画拓扑 → 编辑设备属性 → 生成/体检/下发

设计: 拓扑节点属性直接存 DeviceConfig 的序列化结果(config 字段),
      生成时零转换, 完全复用现有厂商生成器与校验器。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.http_util import attachment_header
from app.db.base import get_session
from app.db.models import Device, Topology, TopologyNode, TopologyLink, AuditLog
from app.services import topology_service as ts

router = APIRouter(prefix="/api/topologies", tags=["拓扑图"])


# --------------------------------------------------------------------------
# 请求模型
# --------------------------------------------------------------------------

class TopologyCreate(BaseModel):
    name: str = Field(..., max_length=128)
    description: str | None = None


class TopologyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    meta: dict | None = None


class NodeCreate(BaseModel):
    name: str = Field(..., max_length=128)
    vendor: str = "huawei"
    device_type: str = "switch"
    x: int = 0
    y: int = 0
    device_id: str | None = None
    config: dict | None = None


class NodeUpdate(BaseModel):
    name: str | None = None
    x: int | None = None
    y: int | None = None
    device_id: str | None = None
    config: dict | None = None
    clear_device: bool = False


class LinkCreate(BaseModel):
    src_node_key: str
    src_port: str | None = None
    dst_node_key: str
    dst_port: str | None = None
    link_type: str = "trunk"
    description: str | None = None


class LinkUpdate(BaseModel):
    src_port: str | None = None
    dst_port: str | None = None
    link_type: str | None = None
    description: str | None = None


class GenerateRequest(BaseModel):
    node_keys: list[str] | None = None


class GraphSnapshot(BaseModel):
    """整图快照(撤销/重做用) — 前端直接回传节点/链路字典"""

    nodes: list[dict] = Field(default_factory=list)
    links: list[dict] = Field(default_factory=list)
    label: str | None = None


# --------------------------------------------------------------------------
# 内部工具
# --------------------------------------------------------------------------

async def _get_topology(session, topology_id: str) -> Topology:
    topo = await session.get(Topology, topology_id)
    if not topo:
        raise HTTPException(404, "拓扑图不存在")
    return topo


async def _load_nodes(session, topology_id: str) -> list[TopologyNode]:
    r = await session.execute(
        select(TopologyNode)
        .where(TopologyNode.topology_id == topology_id)
        .order_by(TopologyNode.created_at)
    )
    return list(r.scalars().all())


async def _load_links(session, topology_id: str) -> list[TopologyLink]:
    r = await session.execute(
        select(TopologyLink)
        .where(TopologyLink.topology_id == topology_id)
        .order_by(TopologyLink.created_at)
    )
    return list(r.scalars().all())


def _node_dict(n: TopologyNode) -> dict:
    cfg = n.config or {}
    basic = cfg.get("basic") or {}
    return {
        "id": n.id,
        "node_key": n.node_key,
        "name": n.name,
        "x": n.x,
        "y": n.y,
        "device_id": n.device_id,
        "vendor": cfg.get("vendor", "huawei"),
        "device_type": cfg.get("device_type", "switch"),
        "mgmt_ip": ((basic.get("mgmt_interface") or {}).get("ip_address")) or "",
        "config": cfg,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def _link_dict(l: TopologyLink) -> dict:
    return {
        "id": l.id,
        "src_node_key": l.src_node_key,
        "src_port": l.src_port,
        "dst_node_key": l.dst_node_key,
        "dst_port": l.dst_port,
        "link_type": l.link_type,
        "description": l.description,
    }


# --------------------------------------------------------------------------
# 拓扑图 CRUD
# --------------------------------------------------------------------------

@router.get("")
async def list_topologies():
    """拓扑图列表(含节点/链路数量)"""
    async with get_session() as session:
        r = await session.execute(select(Topology).order_by(Topology.updated_at.desc()))
        topos = list(r.scalars().all())
        out = []
        for t in topos:
            nodes = await _load_nodes(session, t.id)
            links = await _load_links(session, t.id)
            out.append(
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "node_count": len(nodes),
                    "link_count": len(links),
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                }
            )
    return {"success": True, "topologies": out}


@router.post("")
async def create_topology(req: TopologyCreate):
    """新建拓扑图"""
    async with get_session() as session:
        topo = Topology(name=req.name, description=req.description, meta={"zoom": 1})
        session.add(topo)
        await session.flush()
        tid = topo.id
        session.add(
            AuditLog(action="topology_create", target=req.name, operator="system", detail={"topology_id": tid})
        )
    return {"success": True, "id": tid, "message": f"拓扑图 “{req.name}” 已创建"}


@router.get("/{topology_id}")
async def get_topology(topology_id: str):
    """获取拓扑图完整内容(节点 + 链路)"""
    async with get_session() as session:
        topo = await _get_topology(session, topology_id)
        nodes = await _load_nodes(session, topology_id)
        links = await _load_links(session, topology_id)
        return {
            "success": True,
            "topology": {
                "id": topo.id,
                "name": topo.name,
                "description": topo.description,
                "meta": topo.meta or {},
                "updated_at": topo.updated_at.isoformat() if topo.updated_at else None,
            },
            "nodes": [_node_dict(n) for n in nodes],
            "links": [_link_dict(l) for l in links],
        }


@router.put("/{topology_id}")
async def update_topology(topology_id: str, req: TopologyUpdate):
    """更新拓扑图(名称/描述/视口)"""
    async with get_session() as session:
        topo = await _get_topology(session, topology_id)
        if req.name is not None:
            topo.name = req.name
        if req.description is not None:
            topo.description = req.description
        if req.meta is not None:
            topo.meta = req.meta
    return {"success": True, "message": "已保存"}


@router.delete("/{topology_id}")
async def delete_topology(topology_id: str):
    """删除拓扑图(连带节点与链路)"""
    async with get_session() as session:
        topo = await _get_topology(session, topology_id)
        name = topo.name
        await session.delete(topo)
        session.add(AuditLog(action="topology_delete", target=name, operator="system"))
    return {"success": True, "message": f"拓扑图 “{name}” 已删除"}


# --------------------------------------------------------------------------
# 节点
# --------------------------------------------------------------------------

@router.post("/{topology_id}/nodes")
async def add_node(topology_id: str, req: NodeCreate):
    """新增设备节点(自动生成默认属性骨架)"""
    async with get_session() as session:
        await _get_topology(session, topology_id)
        nodes = await _load_nodes(session, topology_id)
        used = {n.node_key for n in nodes}
        i = 1
        while f"node-{i}" in used:
            i += 1
        node_key = f"node-{i}"

        config = req.config or ts.default_node_config(req.vendor, req.device_type, req.name)
        node = TopologyNode(
            topology_id=topology_id,
            node_key=node_key,
            name=req.name,
            x=req.x,
            y=req.y,
            device_id=req.device_id,
            config=config,
        )
        session.add(node)
        await session.flush()
        out = _node_dict(node)
    return {"success": True, "node": out}


@router.put("/{topology_id}/nodes/{node_id}")
async def update_node(topology_id: str, node_id: str, req: NodeUpdate):
    """更新节点(位置/名称/属性/绑定设备)"""
    async with get_session() as session:
        node = await session.get(TopologyNode, node_id)
        if not node or node.topology_id != topology_id:
            raise HTTPException(404, "节点不存在")
        if req.name is not None:
            node.name = req.name
        if req.x is not None:
            node.x = req.x
        if req.y is not None:
            node.y = req.y
        if req.clear_device:
            node.device_id = None
        elif req.device_id is not None:
            node.device_id = req.device_id
        if req.config is not None:
            node.config = req.config
        await session.flush()
        out = _node_dict(node)
    return {"success": True, "node": out}


@router.delete("/{topology_id}/nodes/{node_id}")
async def delete_node(topology_id: str, node_id: str):
    """删除节点(连带删除其所有链路)"""
    async with get_session() as session:
        node = await session.get(TopologyNode, node_id)
        if not node or node.topology_id != topology_id:
            raise HTTPException(404, "节点不存在")
        node_key = node.node_key
        await session.delete(node)
        r = await session.execute(
            select(TopologyLink).where(
                TopologyLink.topology_id == topology_id,
            )
        )
        removed = 0
        for l in r.scalars().all():
            if l.src_node_key == node_key or l.dst_node_key == node_key:
                await session.delete(l)
                removed += 1
    return {"success": True, "message": f"节点已删除(连带 {removed} 条链路)"}


# --------------------------------------------------------------------------
# 链路
# --------------------------------------------------------------------------

@router.post("/{topology_id}/links")
async def add_link(topology_id: str, req: LinkCreate):
    """新增链路"""
    async with get_session() as session:
        await _get_topology(session, topology_id)
        nodes = await _load_nodes(session, topology_id)
        keys = {n.node_key for n in nodes}
        if req.src_node_key not in keys or req.dst_node_key not in keys:
            raise HTTPException(400, "链路两端的节点不存在")
        if req.src_node_key == req.dst_node_key:
            raise HTTPException(400, "不允许自环链路")

        link = TopologyLink(
            topology_id=topology_id,
            src_node_key=req.src_node_key,
            src_port=req.src_port,
            dst_node_key=req.dst_node_key,
            dst_port=req.dst_port,
            link_type=req.link_type,
            description=req.description,
        )
        session.add(link)
        await session.flush()
        # 端口为空时自动补全(服务内部会就地写回链路与节点配置)
        autofill_result = None
        if not req.src_port or not req.dst_port:
            links = await _load_links(session, topology_id)
            autofill_result = ts.autofill_link_ports(nodes, links, apply_config=True)
            await session.flush()
        out = _link_dict(link)
        node_snapshots = [_node_dict(n) for n in nodes]
    msg = "链路已创建"
    if autofill_result and autofill_result.get("failures"):
        names = "、".join(dict.fromkeys(f["node"] for f in autofill_result["failures"]))
        msg = f"链路已创建，但 {names} 的端口已被占满，请在链路属性中手动指定端口"
    return {"success": True, "message": msg, "link": out, "nodes": node_snapshots}


@router.put("/{topology_id}/links/{link_id}")
async def update_link(topology_id: str, link_id: str, req: LinkUpdate):
    """更新链路(端口/类型)"""
    async with get_session() as session:
        link = await session.get(TopologyLink, link_id)
        if not link or link.topology_id != topology_id:
            raise HTTPException(404, "链路不存在")
        if req.src_port is not None:
            link.src_port = req.src_port
        if req.dst_port is not None:
            link.dst_port = req.dst_port
        if req.link_type is not None:
            link.link_type = req.link_type
        if req.description is not None:
            link.description = req.description
        await session.flush()
        out = _link_dict(link)
    return {"success": True, "link": out}


@router.delete("/{topology_id}/links/{link_id}")
async def delete_link(topology_id: str, link_id: str):
    """删除链路"""
    async with get_session() as session:
        link = await session.get(TopologyLink, link_id)
        if not link or link.topology_id != topology_id:
            raise HTTPException(404, "链路不存在")
        await session.delete(link)
    return {"success": True, "message": "链路已删除"}


# --------------------------------------------------------------------------
# 快照覆盖(撤销 / 重做)
# --------------------------------------------------------------------------

def _coerce_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


@router.put("/{topology_id}/graph")
async def replace_graph(topology_id: str, req: GraphSnapshot):
    """用快照整体覆盖拓扑 —— 撤销/重做专用

    按 id 对齐而不是"全删重建": 快照里有、库里没有的补建(保留原 id/node_key),
    库里多出来的删除, 其余整条覆盖; 这样 node_key 与"已绑定受管设备"的 device_id
    都能原样保留, 撤销后不会掉绑定。
    """
    async with get_session() as session:
        await _get_topology(session, topology_id)
        cur_nodes = {n.id: n for n in await _load_nodes(session, topology_id)}
        cur_links = {l.id: l for l in await _load_links(session, topology_id)}

        keep_keys: set[str] = set()
        created_nodes = 0
        for raw in req.nodes:
            key = str(raw.get("node_key") or "").strip()
            if not key:
                continue
            keep_keys.add(key)
            nid = str(raw.get("id") or "").strip()
            node = cur_nodes.get(nid) if nid else None
            if node is None:
                node = next((n for n in cur_nodes.values() if n.node_key == key), None)
            if node is None:
                # 补建时沿用快照里的 id(node_key 与 id 都尽量稳定, 前端/绑定关系不受影响)
                node = TopologyNode(topology_id=topology_id, node_key=key, **({"id": nid} if nid else {}))
                session.add(node)
                created_nodes += 1
            node.node_key = key
            node.name = str(raw.get("name") or key)
            node.x = _coerce_int(raw.get("x"))
            node.y = _coerce_int(raw.get("y"))
            node.device_id = raw.get("device_id") or None
            if isinstance(raw.get("config"), dict):
                node.config = raw["config"]
        await session.flush()

        removed_nodes = 0
        for n in list(cur_nodes.values()):
            if n.node_key not in keep_keys:
                await session.delete(n)
                removed_nodes += 1

        keep_links: set[str] = set()
        for raw in req.links:
            s_key = str(raw.get("src_node_key") or "")
            d_key = str(raw.get("dst_node_key") or "")
            if s_key not in keep_keys or d_key not in keep_keys or s_key == d_key:
                continue  # 端点不存在或自环 → 丢弃(快照与节点集不同步时的兜底)
            lid = str(raw.get("id") or "").strip()
            if not lid:
                continue
            keep_links.add(lid)
            link = cur_links.get(lid)
            if link is None:
                link = TopologyLink(topology_id=topology_id, id=lid)
                session.add(link)
            link.src_node_key = s_key
            link.src_port = raw.get("src_port") or None
            link.dst_node_key = d_key
            link.dst_port = raw.get("dst_port") or None
            link.link_type = raw.get("link_type") or "trunk"
            link.description = raw.get("description") or None

        removed_links = 0
        r = await session.execute(
            select(TopologyLink).where(TopologyLink.topology_id == topology_id)
        )
        for l in r.scalars().all():
            if l.id not in keep_links:
                await session.delete(l)
                removed_links += 1
        await session.flush()

        session.add(
            AuditLog(
                action="topology_history_apply",
                target=topology_id,
                operator="system",
                detail={
                    "label": req.label,
                    "nodes": len(keep_keys),
                    "links": len(keep_links),
                    "created_nodes": created_nodes,
                    "removed_nodes": removed_nodes,
                    "removed_links": removed_links,
                },
            )
        )
        nodes = await _load_nodes(session, topology_id)
        links = await _load_links(session, topology_id)
        node_out = [_node_dict(n) for n in nodes]
        link_out = [_link_dict(l) for l in links]
    return {"success": True, "message": "已恢复到该步骤", "nodes": node_out, "links": link_out}


# --------------------------------------------------------------------------
# 生成 / 体检 / 导出
# --------------------------------------------------------------------------

@router.post("/{topology_id}/generate")
async def generate(topology_id: str, req: GenerateRequest):
    """生成配置 — 指定 node_keys 则只生成选中设备, 否则整图生成"""
    async with get_session() as session:
        await _get_topology(session, topology_id)
        nodes = await _load_nodes(session, topology_id)
        if req.node_keys:
            nodes = [n for n in nodes if n.node_key in set(req.node_keys)]
        if not nodes:
            raise HTTPException(400, "拓扑中没有可生成的节点")
        result = ts.generate_topology(nodes, None)
        session.add(
            AuditLog(
                action="topology_generate",
                target=topology_id,
                operator="system",
                detail={"total": result["total"], "ok": result["ok"]},
            )
        )
    return result


@router.post("/{topology_id}/check")
async def check(topology_id: str):
    """拓扑体检 — 端口占用 / IP 冲突 / VLAN 未定义 / 链路两端不一致 等"""
    async with get_session() as session:
        await _get_topology(session, topology_id)
        nodes = await _load_nodes(session, topology_id)
        links = await _load_links(session, topology_id)
        r = await session.execute(select(Device.host).where(Device.host.is_not(None)))
        managed = {h for h in r.scalars().all() if h}
    result = ts.check_topology(nodes, links, managed)
    result["node_summaries"] = [ts.node_summary(n) for n in nodes]
    return result


@router.post("/{topology_id}/autofill-ports")
async def autofill_ports(topology_id: str):
    """按链路自动补全端口名, 并写入节点 VLAN 接口配置"""
    async with get_session() as session:
        await _get_topology(session, topology_id)
        nodes = await _load_nodes(session, topology_id)
        links = await _load_links(session, topology_id)
        if not links:
            return {"success": False, "message": "拓扑中还没有链路"}
        upd = ts.autofill_link_ports(nodes, links, apply_config=True)
        await session.flush()
        link_snapshots = [_link_dict(l) for l in links]
        node_snapshots = [_node_dict(n) for n in nodes]
    msg = f"已补全 {upd['changed']} 条链路的端口并写入接口配置"
    if upd.get("failures"):
        names = "、".join(dict.fromkeys(f["node"] for f in upd["failures"]))
        msg += f"；{names} 的端口已被占满，无法自动分配"
    return {
        "success": True,
        "message": msg,
        "links": link_snapshots,
        "nodes": node_snapshots,
    }


@router.get("/{topology_id}/export")
async def export_topology(topology_id: str):
    """导出整图配置为 zip (每台一个 .cfg + 拓扑清单)"""
    async with get_session() as session:
        topo = await _get_topology(session, topology_id)
        nodes = await _load_nodes(session, topology_id)
        links = await _load_links(session, topology_id)
        if not nodes:
            raise HTTPException(400, "拓扑中没有节点")
        data = ts.export_zip(topo, nodes, links)
        name = topo.name
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": attachment_header(f"{name}_configs.zip")},
    )

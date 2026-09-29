"""ORM 数据模型 — 设备、配置版本、审计日志"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime.datetime:
    """本地时间 (北京时间) — 直接存本地时间, 前端无需再做时区换算"""
    return datetime.datetime.now()


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    vendor: Mapped[str] = mapped_column(String(32), nullable=False)
    device_type: Mapped[str] = mapped_column(String(32), nullable=False, default="switch")
    connection_type: Mapped[str] = mapped_column(String(16), nullable=False, default="ssh")
    host: Mapped[str] = mapped_column(String(128), nullable=True)
    port: Mapped[int] = mapped_column(Integer, nullable=True, default=22)
    username: Mapped[str] = mapped_column(String(64), nullable=True)
    password: Mapped[str] = mapped_column(String(256), nullable=True)
    enable_password: Mapped[str] = mapped_column(String(256), nullable=True)
    location: Mapped[str] = mapped_column(String(256), nullable=True)
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_now
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )

    configs: Mapped[list["DeviceConfig"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class DeviceConfig(Base):
    __tablename__ = "device_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    config_text: Mapped[str] = mapped_column(Text, nullable=False)
    version_label: Mapped[str] = mapped_column(String(128), nullable=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    pushed_by: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_now
    )

    device: Mapped["Device"] = relationship(back_populates="configs")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_now
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(128), nullable=True)
    operator: Mapped[str] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="success")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_now
    )


class Topology(Base):
    """拓扑图 — 一张图一条记录, 节点属性直接存 DeviceConfig 序列化结果"""

    __tablename__ = "topologies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    # 画布视口 {zoom, tx, ty} 与前端附加元数据
    meta: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )

    nodes: Mapped[list["TopologyNode"]] = relationship(
        back_populates="topology", cascade="all, delete-orphan"
    )
    links: Mapped[list["TopologyLink"]] = relationship(
        back_populates="topology", cascade="all, delete-orphan"
    )


class TopologyNode(Base):
    """拓扑节点 — 一个网络设备(交换机/路由器/AP)"""

    __tablename__ = "topology_nodes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    topology_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False
    )
    # 前端画布中的节点 ID (稳定标识, 链路用它关联)
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="device")
    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    # 可选: 关联受管设备(devices 表), 用于备份/下发
    device_id: Mapped[str] = mapped_column(String(32), nullable=True)
    # 完整 DeviceConfig 序列化 (vendor/device_type/hostname/basic/vlan/routing/security/interface)
    config: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )

    topology: Mapped["Topology"] = relationship(back_populates="nodes")


class TopologyLink(Base):
    """拓扑链路 — 两个节点端口之间的连接"""

    __tablename__ = "topology_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    topology_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False
    )
    src_node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    src_port: Mapped[str] = mapped_column(String(64), nullable=True)
    dst_node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    dst_port: Mapped[str] = mapped_column(String(64), nullable=True)
    # trunk / access / 未指定
    link_type: Mapped[str] = mapped_column(String(16), default="trunk")
    description: Mapped[str] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    topology: Mapped["Topology"] = relationship(back_populates="links")

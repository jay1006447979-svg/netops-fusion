"""数据库基础 — SQLAlchemy 异步引擎与会话"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """初始化数据库表"""
    from app.db import models  # noqa: F401 — 确保模型被加载

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 轻量迁移: 旧库 device_configs 表补 file_path 列 (create_all 不会修改已存在的表)
        from sqlalchemy import text

        try:
            await conn.execute(
                text("ALTER TABLE device_configs ADD COLUMN file_path VARCHAR(512)")
            )
        except Exception:
            pass  # 列已存在

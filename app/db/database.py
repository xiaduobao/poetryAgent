"""异步数据库引擎与会话。"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import ROOT_DIR, get_settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def _db_url() -> str:
    settings = get_settings()
    if settings.database_url:
        url = settings.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    db_path = Path(settings.sessions_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


def _engine_kwargs() -> dict:
    url = _db_url()
    kwargs: dict = {"echo": False}
    if url.startswith("postgresql"):
        kwargs.update(pool_size=10, max_overflow=20)
    return kwargs


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(_db_url(), **_engine_kwargs())
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


def _alembic_config() -> Config:
    return Config(str(ROOT_DIR / "alembic.ini"))


async def _has_table(conn, table_name: str) -> bool:
    url = _db_url()
    if url.startswith("sqlite"):
        result = await conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
            ),
            {"name": table_name},
        )
        return result.fetchone() is not None
    result = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :name"
        ),
        {"name": table_name},
    )
    return result.fetchone() is not None


async def _maybe_stamp_legacy_schema() -> None:
    """将 create_all 时代遗留的库标记为当前迁移版本，避免 upgrade 重复建表。"""
    async with get_engine().connect() as conn:
        if await _has_table(conn, "alembic_version"):
            return
        if not await _has_table(conn, "users"):
            return
    logger.info("Legacy schema detected without alembic_version; stamping head.")
    await asyncio.to_thread(command.stamp, _alembic_config(), "head")


def run_alembic_upgrade() -> None:
    command.upgrade(_alembic_config(), "head")


async def init_db() -> None:
    await _maybe_stamp_legacy_schema()
    await asyncio.to_thread(run_alembic_upgrade)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db() -> bool:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

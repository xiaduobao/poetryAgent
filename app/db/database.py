"""异步数据库引擎与会话。"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import subprocess
import sys
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
HEAD_REVISION = "001"


def _sqlite_path() -> Path:
    settings = get_settings()
    path = Path(settings.sessions_db)
    if not path.is_absolute():
        path = ROOT_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _db_url() -> str:
    settings = get_settings()
    if settings.database_url:
        url = settings.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    return f"sqlite+aiosqlite:///{_sqlite_path()}"


def _is_sqlite() -> bool:
    return _db_url().startswith("sqlite")


def _engine_kwargs() -> dict:
    url = _db_url()
    kwargs: dict = {"echo": False}
    if url.startswith("postgresql"):
        kwargs.update(pool_size=10, max_overflow=20)
    elif url.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": 30}
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


async def _dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def _sqlite_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _sqlite_current_revision() -> str | None:
    path = _sqlite_path()
    if not path.exists():
        return None
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        if not _sqlite_table_exists(conn, "alembic_version"):
            return None
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return str(row[0]) if row else None
    finally:
        conn.close()


def _maybe_stamp_legacy_schema_sync() -> None:
    path = _sqlite_path()
    if not path.exists():
        return
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        has_version = _sqlite_table_exists(conn, "alembic_version")
        has_users = _sqlite_table_exists(conn, "users")
    finally:
        conn.close()
    if has_version or not has_users:
        return
    logger.info("Legacy schema detected without alembic_version; stamping head.")
    command.stamp(_alembic_config(), "head")


def _run_alembic_subprocess() -> None:
    """独立子进程跑迁移，避免与 uvicorn 事件循环 / aiosqlite 争锁。"""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.stdout:
        for line in result.stdout.strip().splitlines():
            logger.info(line)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"alembic upgrade failed: {detail}")


async def _postgres_current_revision() -> str | None:
    engine = get_engine()
    async with engine.connect() as conn:
        exists = await conn.execute(
            text(
                "SELECT EXISTS ("
                " SELECT FROM information_schema.tables"
                " WHERE table_schema = 'public' AND table_name = 'alembic_version'"
                ")"
            )
        )
        if not exists.scalar():
            return None
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        return str(row[0]) if row else None


async def init_db() -> None:
    await _dispose_engine()

    backend = "SQLite" if _is_sqlite() else "PostgreSQL"
    current = _sqlite_current_revision() if _is_sqlite() else await _postgres_current_revision()
    if current == HEAD_REVISION:
        logger.info("%s schema already at revision %s, skip migration.", backend, HEAD_REVISION)
        return
    if current:
        logger.info("%s at revision %s, upgrading to head.", backend, current)

    if _is_sqlite():
        await asyncio.to_thread(_maybe_stamp_legacy_schema_sync)
        current = _sqlite_current_revision()
        if current == HEAD_REVISION:
            logger.info("SQLite schema stamped at head.")
            return

    logger.info("Running alembic upgrade in subprocess...")
    await asyncio.to_thread(_run_alembic_subprocess)
    logger.info("Database migrations applied.")


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

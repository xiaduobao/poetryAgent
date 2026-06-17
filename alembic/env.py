"""Alembic 环境配置。"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, event, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import ROOT_DIR, get_settings
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# 与 app/db/database.py 保持一致
HEAD_REVISION = "001"


def _sqlite_path() -> Path:
    settings = get_settings()
    path = Path(settings.sessions_db)
    if not path.is_absolute():
        path = ROOT_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _sync_sqlite_url(url: str) -> str:
    if url.startswith("sqlite+aiosqlite:///"):
        return url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
    return url


def _get_url() -> str:
    settings = get_settings()
    if settings.database_url:
        url = settings.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    return f"sqlite+aiosqlite:///{_sqlite_path()}"


def _sqlite_engine():
    return create_engine(
        _sync_sqlite_url(_get_url()),
        poolclass=pool.NullPool,
        connect_args={"timeout": 30, "check_same_thread": False},
    )


def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(
        url=_sync_sqlite_url(url) if url.startswith("sqlite") else url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    url = _get_url()
    if url.startswith("sqlite"):
        connectable = _sqlite_engine()

        @event.listens_for(connectable, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        with connectable.connect() as connection:
            do_run_migrations(connection)
        connectable.dispose()
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

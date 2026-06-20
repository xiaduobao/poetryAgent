"""LangGraph Checkpoint 工厂。"""
from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings

logger = logging.getLogger(__name__)

_checkpointer: Any = None
_checkpointer_cm: Any = None
_checkpointer_backend: str = ""


def get_checkpointer():
    """返回已初始化的 checkpointer；未 setup 时降级为 MemorySaver。"""
    if _checkpointer is not None:
        return _checkpointer
    logger.warning("Checkpointer not initialized; using in-memory fallback")
    return MemorySaver()


def checkpointer_backend() -> str:
    return _checkpointer_backend or "memory"


async def _close_checkpointer_cm() -> None:
    global _checkpointer, _checkpointer_cm
    if _checkpointer_cm is not None:
        try:
            await _checkpointer_cm.__aexit__(None, None, None)
        except Exception as e:
            logger.warning("Error closing checkpointer context: %s", e)
    _checkpointer = None
    _checkpointer_cm = None


async def setup_checkpointer() -> None:
    """在 FastAPI lifespan 启动时初始化 Postgres → Redis → MemorySaver。"""
    global _checkpointer, _checkpointer_cm, _checkpointer_backend

    if _checkpointer is not None:
        return

    settings = get_settings()
    db_url = settings.database_url or ""

    if db_url.startswith("postgresql"):
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            conn_str = db_url.replace("postgresql+asyncpg://", "postgresql://")
            _checkpointer_cm = AsyncPostgresSaver.from_conn_string(conn_str)
            _checkpointer = await _checkpointer_cm.__aenter__()
            await _checkpointer.setup()
            _checkpointer_backend = "postgres"
            logger.info("Using Postgres checkpointer")
            return
        except Exception as e:
            logger.warning("Postgres checkpointer unavailable: %s", e)
            await _close_checkpointer_cm()
            _checkpointer_backend = ""

    if settings.redis_url:
        try:
            from langgraph.checkpoint.redis.aio import AsyncRedisSaver

            _checkpointer_cm = AsyncRedisSaver.from_conn_string(settings.redis_url)
            _checkpointer = await _checkpointer_cm.__aenter__()
            await _checkpointer.setup()
            _checkpointer_backend = "redis"
            logger.info("Using Redis checkpointer")
            return
        except Exception as e:
            logger.warning("Redis checkpointer unavailable: %s", e)
            await _close_checkpointer_cm()
            _checkpointer_backend = ""

    _checkpointer = MemorySaver()
    _checkpointer_backend = "memory"
    logger.info("Using in-memory checkpointer")


async def shutdown_checkpointer() -> None:
    """关闭 checkpointer 连接（lifespan 退出时调用）。"""
    global _checkpointer_backend
    backend = _checkpointer_backend
    await _close_checkpointer_cm()
    _checkpointer_backend = ""
    if backend:
        logger.info("Checkpointer (%s) closed.", backend)


async def clear_thread_checkpoint(thread_id: str) -> None:
    cp = get_checkpointer()
    if hasattr(cp, "adelete_thread"):
        await cp.adelete_thread(thread_id)
        return
    if hasattr(cp, "storage"):
        keys = [k for k in cp.storage if k[0] == thread_id]
        for key in keys:
            del cp.storage[key]

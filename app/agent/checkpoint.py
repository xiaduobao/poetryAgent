"""LangGraph Checkpoint 工厂。"""
from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings

logger = logging.getLogger(__name__)

_checkpointer = None
_checkpointer_ctx = None


def get_checkpointer():
    global _checkpointer, _checkpointer_ctx
    if _checkpointer is not None:
        return _checkpointer

    settings = get_settings()
    db_url = settings.database_url or ""

    if db_url.startswith("postgresql"):
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            conn_str = db_url.replace("postgresql+asyncpg://", "postgresql://")
            _checkpointer_ctx = AsyncPostgresSaver.from_conn_string(conn_str)
            _checkpointer = _checkpointer_ctx.__enter__()
            logger.info("Using Postgres checkpointer")
            return _checkpointer
        except Exception as e:
            logger.warning("Postgres checkpointer unavailable, using memory: %s", e)

    if settings.redis_url:
        try:
            from langgraph.checkpoint.redis.aio import AsyncRedisSaver

            _checkpointer_ctx = AsyncRedisSaver.from_conn_string(settings.redis_url)
            _checkpointer = _checkpointer_ctx.__enter__()
            logger.info("Using Redis checkpointer")
            return _checkpointer
        except Exception as e:
            logger.warning("Redis checkpointer unavailable, using memory: %s", e)

    _checkpointer = MemorySaver()
    logger.info("Using in-memory checkpointer")
    return _checkpointer


async def setup_checkpointer() -> None:
    cp = get_checkpointer()
    if hasattr(cp, "setup"):
        await cp.setup()


async def clear_thread_checkpoint(thread_id: str) -> None:
    cp = get_checkpointer()
    if hasattr(cp, "adelete_thread"):
        await cp.adelete_thread(thread_id)
        return
    if hasattr(cp, "storage"):
        keys = [k for k in cp.storage if k[0] == thread_id]
        for key in keys:
            del cp.storage[key]

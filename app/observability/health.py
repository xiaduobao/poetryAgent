"""深度健康检查。"""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage

from app.agent.llm import get_llm
from app.config import get_settings
from app.db.database import check_db

logger = logging.getLogger(__name__)


async def check_chroma() -> bool:
    try:
        from app.rag.indexer import get_vector_store

        store = get_vector_store()
        if store is None:
            return False
        coll = store._collection  # noqa: SLF001
        return coll.count() >= 0
    except Exception as e:
        logger.warning("chroma health check failed: %s", e)
        return False


async def check_llm() -> bool:
    settings = get_settings()
    if not settings.openai_api_key or settings.openai_api_key == "sk-placeholder":
        return False
    try:
        llm = get_llm()
        await llm.ainvoke([HumanMessage(content="ping")])
        return True
    except Exception as e:
        logger.warning("llm health check failed: %s", e)
        return False


async def check_redis() -> bool | None:
    settings = get_settings()
    if not settings.redis_url:
        return None
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        return True
    except Exception as e:
        logger.warning("redis health check failed: %s", e)
        return False


async def readiness_report() -> dict:
    db_ok = await check_db()
    chroma_ok = await check_chroma()
    llm_ok = await check_llm()
    redis_ok = await check_redis()

    checks = {
        "database": db_ok,
        "chroma": chroma_ok,
        "llm": llm_ok,
    }
    if redis_ok is not None:
        checks["redis"] = redis_ok

    all_ok = all(checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}

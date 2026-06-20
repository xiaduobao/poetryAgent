"""Checkpoint 初始化测试。"""
from __future__ import annotations

import pytest

from app.agent import checkpoint as cp_mod
from app.config import get_settings
from langgraph.checkpoint.memory import MemorySaver


@pytest.fixture(autouse=True)
def _reset_checkpoint_module():
    yield
    cp_mod._checkpointer = None
    cp_mod._checkpointer_cm = None
    cp_mod._checkpointer_backend = ""
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_setup_checkpointer_postgres(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://poetry:poetry@localhost:5432/poetry_agent",
    )
    monkeypatch.setenv("REDIS_URL", "")
    get_settings.cache_clear()

    await cp_mod.setup_checkpointer()
    saver = cp_mod.get_checkpointer()
    assert cp_mod.checkpointer_backend() == "postgres"
    assert type(saver).__name__ == "AsyncPostgresSaver"
    await cp_mod.shutdown_checkpointer()


@pytest.mark.asyncio
async def test_get_checkpointer_fallback_before_setup():
    assert isinstance(cp_mod.get_checkpointer(), MemorySaver)
    assert cp_mod.checkpointer_backend() == "memory"


@pytest.mark.asyncio
async def test_commit_agent_state_sets_as_node(monkeypatch):
    from langchain_core.messages import AIMessage, HumanMessage

    from app.agent import graph as graph_mod
    from app.agent.graph import commit_agent_state

    cp_mod._checkpointer = MemorySaver()
    cp_mod._checkpointer_backend = "memory"
    graph_mod._graph = None

    prepared = {
        "state": {
            "messages": [HumanMessage(content="你好")],
            "rag_context": "ctx",
            "tool_result": "",
            "filters": {},
            "source_refs": [],
            "sub_queries": [],
            "is_compound": False,
            "primary_intent": "rag",
            "original_query": "你好",
        },
        "intent": "rag",
        "mode": "rag",
    }
    await commit_agent_state("thread-1", "你好", "回复", prepared)

    snap = await graph_mod.get_agent_graph().aget_state(
        {"configurable": {"thread_id": "thread-1"}}
    )
    assert snap.values["rag_context"] == "ctx"
    assert len(snap.values["messages"]) == 2
    assert isinstance(snap.values["messages"][0], HumanMessage)
    assert isinstance(snap.values["messages"][1], AIMessage)
    graph_mod._graph = None

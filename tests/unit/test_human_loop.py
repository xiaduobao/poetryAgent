"""Human-in-the-loop 单元测试。"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.graph import apply_hitl_tool_decision
from app.agent.human_loop import (
    build_interrupt_payload,
    clear_pending,
    deserialize_prepared,
    format_tool_calls,
    get_pending,
    message_requests_hitl,
    pop_pending,
    prepare_agent_message,
    save_pending,
    serialize_prepared,
    should_defer_hitl,
    strip_hitl_trigger,
)


def test_message_requests_hitl():
    assert message_requests_hitl("human_loop 介绍杜甫")
    assert message_requests_hitl("HUMAN_LOOP 介绍杜甫")
    assert not message_requests_hitl("介绍杜甫")


def test_strip_hitl_trigger():
    assert strip_hitl_trigger("human_loop 介绍杜甫") == "介绍杜甫"
    assert strip_hitl_trigger("请 human_loop 介绍李白") == "请 介绍李白"


def test_should_defer_hitl_requires_keyword_and_config(monkeypatch):
    monkeypatch.setenv("HUMAN_IN_LOOP_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    assert should_defer_hitl("human_loop 介绍杜甫")
    assert not should_defer_hitl("介绍杜甫")

    monkeypatch.setenv("HUMAN_IN_LOOP_ENABLED", "false")
    get_settings.cache_clear()
    assert not should_defer_hitl("human_loop 介绍杜甫")


def test_prepare_agent_message(monkeypatch):
    monkeypatch.setenv("HUMAN_IN_LOOP_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    msg, hitl = prepare_agent_message("human_loop 介绍杜甫")
    assert msg == "介绍杜甫"
    assert hitl is True


def test_format_tool_calls_summary():
    tool_calls = [
        {"name": "author_query", "args": {"name": "杜甫"}, "id": "tc1"},
    ]
    out = format_tool_calls(tool_calls)
    assert out[0]["label"] == "作者查询"
    assert "杜甫" in out[0]["summary"]


def test_pending_store_roundtrip():
    clear_pending("t-hitl")
    prepared = {
        "state": {
            "messages": [
                HumanMessage(content="介绍杜甫"),
                AIMessage(content="", tool_calls=[{"name": "author_query", "args": {"name": "杜甫"}, "id": "1"}]),
            ],
            "rag_context": "",
            "tool_result": "",
            "filters": {},
            "source_refs": [],
        },
        "intent": "tool_author",
        "mode": "hitl_tool_approval",
    }
    tool_calls = format_tool_calls(prepared["state"]["messages"][-1].tool_calls)
    save_pending("t-hitl", prepared, user_message="介绍杜甫", tool_calls=tool_calls)
    assert get_pending("t-hitl") is not None

    pending = pop_pending("t-hitl")
    assert pending is not None
    restored = deserialize_prepared(pending["prepared"])
    assert restored["intent"] == "tool_author"
    assert isinstance(restored["state"]["messages"][0], HumanMessage)


def test_serialize_prepared_preserves_user_message():
    prepared = {
        "state": {"messages": [HumanMessage(content="你好")], "filters": {}},
        "intent": "chat",
        "mode": "chat",
    }
    data = serialize_prepared(prepared, user_message="你好")
    assert data["user_message"] == "你好"


def test_build_interrupt_payload():
    prepared = {"intent": "tool_author", "mode": "hitl_tool_approval", "state": {}}
    payload = build_interrupt_payload(
        "sess-1",
        prepared,
        [{"name": "author_query", "summary": "查询作者：杜甫"}],
    )
    assert payload["session_id"] == "sess-1"
    assert payload["type"] == "tool_approval"


def test_apply_hitl_reject_skips_tools():
    prepared = {
        "state": {
            "messages": [
                HumanMessage(content="介绍杜甫"),
                AIMessage(content="", tool_calls=[{"name": "author_query", "args": {"name": "杜甫"}, "id": "1"}]),
            ],
            "filters": {},
        },
        "intent": "tool_author",
        "mode": "hitl_tool_approval",
    }
    out = apply_hitl_tool_decision(prepared, "reject")
    assert out["mode"] == "tool_summary"
    assert "拒绝" in out["state"]["tool_result"]


def test_apply_hitl_approve_runs_tools(monkeypatch):
    from app.agent import graph as graph_mod

    monkeypatch.setattr(
        graph_mod,
        "_run_tools",
        lambda state: [],
    )
    prepared = {
        "state": {
            "messages": [
                HumanMessage(content="介绍杜甫"),
                AIMessage(content="", tool_calls=[{"name": "author_query", "args": {"name": "杜甫"}, "id": "1"}]),
            ],
            "filters": {},
        },
        "intent": "tool_author",
        "mode": "hitl_tool_approval",
    }
    out = apply_hitl_tool_decision(prepared, "approve")
    assert out["mode"] == "tool_summary"

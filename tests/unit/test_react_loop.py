"""有限 ReAct 单元测试。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.react_loop import (
    should_react_fallback,
    should_use_react_tool_loop,
    run_limited_react,
)


def _state(message: str) -> dict:
    return {
        "messages": [HumanMessage(content=message)],
        "intent": "tool_meter",
        "rag_context": "",
        "tool_result": "",
        "filters": {},
        "source_refs": [],
    }


def test_should_react_fallback_rule_misses():
    assert should_react_fallback("rule", 0.5) is False


def test_should_react_fallback_low_llm_confidence(monkeypatch):
    monkeypatch.setenv("REACT_ENABLED", "true")
    monkeypatch.setenv("REACT_LOW_CONFIDENCE_FALLBACK", "true")
    monkeypatch.setenv("REACT_LOW_CONFIDENCE_THRESHOLD", "0.65")
    from app.config import get_settings

    get_settings.cache_clear()
    assert should_react_fallback("llm", 0.5) is True
    assert should_react_fallback("llm", 0.9) is False
    get_settings.cache_clear()


def test_should_use_react_tool_loop_high_confidence_rule(monkeypatch):
    monkeypatch.setenv("REACT_ENABLED", "true")
    monkeypatch.setenv("REACT_TOOL_LOOP_ENABLED", "true")
    monkeypatch.setenv("REACT_LOW_CONFIDENCE_THRESHOLD", "0.65")
    from app.config import get_settings

    get_settings.cache_clear()
    assert (
        should_use_react_tool_loop(
            "rule",
            0.92,
            intent="tool_meter",
            query="分析静夜思的格律",
        )
        is False
    )
    get_settings.cache_clear()


def test_should_use_react_tool_loop_anaphora(monkeypatch):
    monkeypatch.setenv("REACT_ENABLED", "true")
    monkeypatch.setenv("REACT_TOOL_LOOP_ENABLED", "true")
    monkeypatch.setenv("REACT_LOW_CONFIDENCE_THRESHOLD", "0.65")
    from app.config import get_settings

    get_settings.cache_clear()
    assert (
        should_use_react_tool_loop(
            "rule",
            0.92,
            intent="tool_meter",
            query="分析这首诗的格律",
        )
        is True
    )
    get_settings.cache_clear()


def test_should_use_react_tool_loop_low_confidence(monkeypatch):
    monkeypatch.setenv("REACT_ENABLED", "true")
    monkeypatch.setenv("REACT_TOOL_LOOP_ENABLED", "true")
    monkeypatch.setenv("REACT_LOW_CONFIDENCE_THRESHOLD", "0.65")
    from app.config import get_settings

    get_settings.cache_clear()
    assert should_use_react_tool_loop("llm", 0.5, intent="tool_author", query="介绍一下") is True
    assert should_use_react_tool_loop("llm", 0.9, intent="tool_author", query="介绍杜甫") is False
    get_settings.cache_clear()


def test_run_limited_react_multi_round(monkeypatch):
    monkeypatch.setenv("REACT_ENABLED", "true")
    monkeypatch.setenv("REACT_MAX_STEPS", "3")
    monkeypatch.setenv("REACT_RAG_AS_TOOL_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()

    call_count = {"n": 0}

    def fake_invoke(messages, config=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "tc1",
                        "name": "poem_lookup",
                        "args": {"title": "静夜思"},
                    }
                ],
            )
        if call_count["n"] == 2:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "tc2",
                        "name": "meter_analysis",
                        "args": {"title": "静夜思", "content": "床前明月光"},
                    }
                ],
            )
        return AIMessage(content="信息已足够")

    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value.invoke = fake_invoke

    with patch("app.agent.react_loop.get_llm", return_value=mock_llm), patch(
        "app.agent.react_loop._execute_tool_calls",
        side_effect=[
            [ToolMessage(content='{"data": {"title": "静夜思"}}', tool_call_id="tc1")],
            [ToolMessage(content='{"title": "静夜思", "found": true}', tool_call_id="tc2")],
        ],
    ):
        result = run_limited_react(
            _state("分析静夜思的格律"),
            reason="tool_loop",
            intent_hint="先查原文再分析格律",
            include_rag_tool=False,
        )

    assert call_count["n"] == 3
    assert result["react_mode"] is True
    assert result["react_steps"] == 3
    assert "静夜思" in result["tool_result"]
    get_settings.cache_clear()

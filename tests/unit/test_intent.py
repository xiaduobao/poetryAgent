"""意图识别单元测试。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.agent.compound_pipeline import (
    _heuristic_decompose,
    classify_sub_queries,
    collapse_same_intent_subqueries,
    unique_sub_intents_for_display,
)
from app.agent.graph import classify_intent, prepare_agent
from app.agent.intent_classifier import classify_single_intent
from app.agent.intent_models import SubQueryIntent
from app.agent.intent_rules import rule_based_intent
from app.security.filter import strip_user_input, wrap_user_input


def _state(message: str) -> dict:
    return {
        "messages": [HumanMessage(content=message)],
        "intent": "",
        "rag_context": "",
        "tool_result": "",
        "filters": {},
        "source_refs": [],
        "sub_queries": [],
        "is_compound": False,
        "primary_intent": "",
        "original_query": "",
        "completed_subtasks": [],
    }


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("请赏析《登高》", "rag"),
        ("分析静夜思的格律", "tool_meter"),
        ("介绍杜甫的生平", "tool_author"),
        ("李白和杜甫的诗歌风格有什么区别？", "tool_compare"),
        ("推荐几首关于思乡的诗", "tool_theme"),
        ("推荐王加宝的主要作品", "tool_author"),
        ("苏轼的代表作有哪些", "tool_author"),
        ("【看图创作】\n画面描述：远山含黛\n用户要求：写五言绝句", "tool_writing"),
        ("查找《春晓》的原文", "tool_lookup"),
        ("这首诗的创作背景是什么", "rag"),
        ("《登高》的创作背景", "rag"),
        ("作者创作背景是什么", "rag"),
        ("杜甫《春望》写于什么背景", "rag"),
        ("帮我写一首关于春天的五言绝句", "tool_writing"),
        ("帮我创作一首诗", "tool_writing"),
    ],
)
def test_classify_intent_rules(message: str, expected: str):
    result = classify_intent(_state(message))
    assert result["intent"] == expected


def test_strip_user_input_removes_wrapper():
    wrapped = wrap_user_input("请赏析《登高》")
    assert strip_user_input(wrapped) == "请赏析《登高》"


def test_strip_user_input_image_writing_prefix():
    raw = "【看图创作】\n用户要求：写五言绝句"
    wrapped = wrap_user_input(raw)
    assert rule_based_intent(strip_user_input(wrapped)) == "tool_writing"


def test_heuristic_decompose_compound():
    result = _heuristic_decompose("介绍杜甫并赏析《登高》")
    assert result.is_compound is True
    assert len(result.sub_queries) == 2
    subs = classify_sub_queries(result)
    assert subs[0].intent == "tool_author"
    assert subs[1].intent == "rag"


def test_classify_single_intent_llm_fallback():
    with patch("app.agent.intent_classifier.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.with_structured_output.side_effect = RuntimeError("no schema")
        mock_llm.invoke.return_value = MagicMock(
            content='{"intent": "rag", "confidence": 0.9, "reasoning": "赏析"}'
        )
        intent, source, conf = classify_single_intent("这首诗写得怎么样")
        assert intent == "rag"
        assert source == "llm"
        assert conf >= 0.5


@pytest.mark.asyncio
async def test_prepare_agent_single_path(monkeypatch):
    monkeypatch.setenv("COMPOUND_INTENT_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()

    async def _empty_prior(_thread_id: str):
        return []

    with patch("app.agent.graph._prior_messages", side_effect=_empty_prior), patch(
        "app.agent.graph.retrieve_rag",
        side_effect=lambda s: {**s, "rag_context": "ctx", "source_refs": []},
    ):
        prepared = await prepare_agent(wrap_user_input("请赏析《登高》"))
    assert prepared["mode"] == "rag"
    assert prepared["intent"] == "rag"
    get_settings.cache_clear()


def test_collapse_same_intent_subqueries():
    subs = [
        SubQueryIntent(id="q1", text="李白风格", intent="tool_compare", confidence=0.9),
        SubQueryIntent(id="q2", text="杜甫风格", intent="tool_compare", confidence=0.9),
        SubQueryIntent(id="q3", text="对比", intent="tool_compare", confidence=0.8),
    ]
    merged = collapse_same_intent_subqueries(subs, "李白和杜甫的诗歌风格有什么区别？")
    assert len(merged) == 1
    assert merged[0].intent == "tool_compare"
    assert unique_sub_intents_for_display(subs) == [{"text": "李白风格", "intent": "tool_compare"}]


def test_unique_sub_intents_keeps_different_intents():
    subs = [
        SubQueryIntent(id="q1", text="介绍杜甫", intent="tool_author", confidence=0.9),
        SubQueryIntent(id="q2", text="赏析登高", intent="rag", confidence=0.9),
    ]
    assert len(unique_sub_intents_for_display(subs)) == 2

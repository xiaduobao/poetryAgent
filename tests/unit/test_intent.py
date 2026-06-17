"""LangGraph 意图识别规则测试（不调用 LLM）。"""
from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from app.agent.graph import classify_intent


def _state(message: str) -> dict:
    return {
        "messages": [HumanMessage(content=message)],
        "intent": "",
        "rag_context": "",
        "tool_result": "",
        "filters": {},
        "source_refs": [],
    }


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("请赏析《登高》", "rag"),
        ("分析静夜思的格律", "tool_meter"),
        ("介绍杜甫的生平", "tool_author"),
        ("李白和杜甫的诗歌风格有什么区别？", "tool_compare"),
        ("推荐几首关于思乡的诗", "tool_theme"),
        ("【看图创作】\n画面描述：远山含黛\n用户要求：写五言绝句", "tool_writing"),
    ],
)
def test_classify_intent_rules(message: str, expected: str):
    result = classify_intent(_state(message))
    assert result["intent"] == expected

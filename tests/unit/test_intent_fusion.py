"""意图融合与上下文增强单元测试。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.intent_classifier import classify_single_intent, prepare_query_for_intent
from app.agent.intent_rules import is_ambiguous_rule_match, match_intent_rules, resolve_rule_match


def test_prepare_query_for_intent_anaphora():
    messages = [
        HumanMessage(content="查找《枫桥夜泊》的原文"),
        AIMessage(content="《枫桥夜泊》张继 …"),
        HumanMessage(content="分析这首诗的格律"),
    ]
    augmented, original = prepare_query_for_intent("分析这首诗的格律", messages)
    assert original == "分析这首诗的格律"
    assert "《枫桥夜泊》" in augmented


def test_classify_meter_with_context_history():
    messages = [
        HumanMessage(content="查找《枫桥夜泊》的原文"),
        AIMessage(content="《枫桥夜泊》张继 …"),
        HumanMessage(content="分析这首诗的格律"),
    ]
    intent, source, conf = classify_single_intent(
        "分析这首诗的格律",
        messages=messages,
    )
    assert intent == "tool_meter"
    assert source in ("rule", "rule+suggested")
    assert conf >= 0.58


def test_fuse_rule_and_suggested_agreement():
    intent, source, conf = classify_single_intent(
        "请赏析《登高》",
        suggested_intent="rag",
        suggested_confidence=0.85,
    )
    assert intent == "rag"
    assert source == "rule+suggested"
    assert conf >= 0.85


def test_suggested_without_rule():
    intent, source, conf = classify_single_intent(
        "随便聊聊",
        suggested_intent="chat",
        suggested_confidence=0.75,
    )
    assert intent == "chat"
    assert source == "suggested"
    assert conf == 0.75


def test_ambiguous_lookup_and_meter():
    text = "查找《静夜思》的原文并分析格律"
    matches = match_intent_rules(text)
    assert is_ambiguous_rule_match(matches) is True
    best, ambiguous = resolve_rule_match(text)
    assert ambiguous is True
    assert best is not None
    assert best.intent == "tool_lookup"
    assert best.confidence <= 0.58


def test_classify_ambiguous_lowers_confidence():
    intent, source, conf = classify_single_intent("查找《静夜思》的原文并分析格律")
    assert intent == "tool_lookup"
    assert source == "rule"
    assert conf <= 0.58


def test_classify_single_intent_llm_when_no_signals():
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

"""对话上下文诗词解析单元测试。"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.context_resolver import (
    augment_query_with_context,
    format_poem_context_hint,
    needs_poem_context,
    resolve_poem_context,
)


def test_needs_poem_context_anaphora():
    assert needs_poem_context("分析这首诗的格律") is True
    assert needs_poem_context("分析《枫桥夜泊》的格律") is False
    assert needs_poem_context("介绍杜甫") is False


def test_resolve_from_prior_user_lookup():
    messages = [
        HumanMessage(content="查找《枫桥夜泊》的原文和注释"),
        AIMessage(content="《枫桥夜泊》张继 … 月落乌啼霜满天，江枫渔火对愁眠。"),
        HumanMessage(content="分析这首诗的格律"),
    ]
    ctx = resolve_poem_context(messages, "分析这首诗的格律")
    assert ctx["title"] == "枫桥夜泊"


def test_resolve_from_tool_message():
    tool_json = (
        '{"found": true, "data": {"title": "静夜思", "author": "李白", '
        '"original": "床前明月光，疑是地上霜。举头望明月，低头思故乡。"}}'
    )
    messages = [
        HumanMessage(content="查找静夜思"),
        AIMessage(content="", tool_calls=[]),
        ToolMessage(content=tool_json, tool_call_id="tc1"),
        AIMessage(content="已找到《静夜思》原文。"),
        HumanMessage(content="分析一下这首诗的格律"),
    ]
    ctx = resolve_poem_context(messages, "分析一下这首诗的格律")
    assert ctx["title"] == "静夜思"
    assert ctx["author"] == "李白"
    assert "床前明月光" in ctx.get("content", "")


def test_format_poem_context_hint():
    hint = format_poem_context_hint({"title": "枫桥夜泊", "author": "张继"})
    assert "枫桥夜泊" in hint
    assert "勿再向用户索要诗题" in hint


def test_augment_query_with_context():
    resolved = {"title": "枫桥夜泊"}
    rewritten = augment_query_with_context("分析这首诗的格律", resolved)
    assert "《枫桥夜泊》" in rewritten

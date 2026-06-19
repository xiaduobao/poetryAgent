"""有限 ReAct 循环：工具多轮、低置信度兜底、RAG-as-tool。"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from app.agent.context_resolver import (
    format_poem_context_hint,
    resolve_poem_context,
)
from app.agent.llm import get_react_llm
from app.agent.prompts import REACT_AGENT_PROMPT, SYSTEM_PROMPT
from app.agent.route_log import log_route
from app.agent.tools import AGENT_TOOLS
from app.config import get_settings
from app.observability.langsmith import get_run_config, traceable, update_run_metadata
from app.rag.retriever import format_context, get_hybrid_retriever
from app.security.filter import strip_user_input

if TYPE_CHECKING:
    from app.agent.graph import AgentState

logger = logging.getLogger(__name__)

INTENT_TOOL_HINTS: dict[str, str] = {
    "tool_author": (
        "请使用 author_query 工具查询作者信息。"
        "若用户询问代表作/作品/名篇，须优先列出 masterpieces 并简要介绍各篇，"
        "不要写成冗长传记。"
    ),
    "tool_meter": (
        "请使用 meter_analysis 工具分析格律。"
        "诗题优先从对话历史（上文《》书名号、工具返回、助手回答）提取；"
        "用户说「这首诗」等指代时，务必结合历史确定诗题。"
        "若缺少原文，先 poem_lookup 再 meter_analysis。"
    ),
    "tool_compare": "请使用 style_compare 工具对比诗人风格。",
    "tool_lookup": "请使用 poem_lookup 工具查找诗词原文、注释或译文。",
    "tool_theme": "请使用 theme_recommend 工具按主题推荐诗词。",
    "tool_allusion": (
        "请使用 allusion_explain 工具解释典故或字词含义。"
        "若需要更多背景，可 poetry_search 检索相关知识库片段。"
    ),
    "tool_writing": (
        "请使用 writing_assistant 工具获取创作指南，再据此为用户创作示例。"
        "若用户提供了画面描述，请以画面意象为主题创作。"
    ),
    "rag": "请使用 poetry_search 检索知识库，再基于检索结果回答鉴赏问题。",
}


class _RagBudget:
    """单次请求内 poetry_search 调用次数上限。"""

    def __init__(self, limit: int) -> None:
        self.remaining = limit
        self.sources: list[dict[str, Any]] = []
        self.contexts: list[str] = []


def _make_poetry_search_tool(
    *,
    filters: dict[str, Any],
    budget: _RagBudget,
) -> StructuredTool:
    def _search(
        query: str,
        author: str = "",
        dynasty: str = "",
        genre: str = "",
    ) -> str:
        if budget.remaining <= 0:
            return json.dumps(
                {"error": "已达本次请求知识库检索次数上限", "doc_count": 0},
                ensure_ascii=False,
            )
        budget.remaining -= 1
        merged_filters = dict(filters)
        if author.strip():
            merged_filters["author"] = author.strip()
        if dynasty.strip():
            merged_filters["dynasty"] = dynasty.strip()
        if genre.strip():
            merged_filters["genre"] = genre.strip()

        retriever = get_hybrid_retriever()
        docs = retriever.retrieve(
            query,
            author=merged_filters.get("author"),
            dynasty=merged_filters.get("dynasty"),
            genre=merged_filters.get("genre"),
        )
        context = format_context(docs)
        sources = [
            {
                "title": d.metadata.get("title"),
                "author": d.metadata.get("author"),
                "snippet": d.page_content[:200],
                "source_file": d.metadata.get("source_file"),
            }
            for d in docs
        ]
        budget.sources.extend(sources)
        if context:
            budget.contexts.append(context)
        return json.dumps(
            {
                "doc_count": len(docs),
                "context": context or "（无检索结果）",
                "sources": sources,
            },
            ensure_ascii=False,
        )

    return StructuredTool.from_function(
        func=_search,
        name="poetry_search",
        description=(
            "检索诗词知识库（混合向量+关键词+Rerank）。"
            "用于鉴赏、赏析、意境分析，或需要知识库背景时。"
            "可选 author/dynasty/genre 过滤。"
        ),
    )


def build_react_tools(
    *,
    filters: dict[str, Any] | None,
    include_rag_tool: bool,
    rag_budget: _RagBudget | None = None,
) -> tuple[list[BaseTool], _RagBudget]:
    budget = rag_budget or _RagBudget(get_settings().react_rag_max_searches)
    tools: list[BaseTool] = list(AGENT_TOOLS)
    if include_rag_tool:
        tools.append(_make_poetry_search_tool(filters=filters or {}, budget=budget))
    return tools, budget


def _execute_tool_calls(
    last: AIMessage,
    tool_map: dict[str, BaseTool],
) -> list[ToolMessage]:
    results: list[ToolMessage] = []
    tool_results_meta: list[dict] = []
    for tc in last.tool_calls:
        name = tc.get("name") if isinstance(tc, dict) else tc.name
        args = tc.get("args") if isinstance(tc, dict) else tc.args
        tool_call_id = tc.get("id") if isinstance(tc, dict) else tc.id

        tool = tool_map.get(name)
        if tool is None:
            content = f"未知工具: {name}"
            tool_results_meta.append({"name": name, "success": False, "error": "unknown_tool"})
        else:
            try:
                content = tool.invoke(args)
                if not isinstance(content, str):
                    content = str(content)
                tool_results_meta.append({"name": name, "success": True})
            except Exception as e:
                logger.warning("react tool %s failed: %s", name, e)
                content = f"工具执行失败: {e}"
                tool_results_meta.append({"name": name, "success": False, "error": str(e)})

        results.append(ToolMessage(content=content, tool_call_id=tool_call_id))

    update_run_metadata(tool_results=tool_results_meta)
    return results


def _last_user_text(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            raw = m.content if isinstance(m.content, str) else str(m.content)
            return strip_user_input(raw)
    return ""


def should_react_fallback(intent_source: str, confidence: float) -> bool:
    """低置信度且非规则命中时走 ReAct 兜底（意图本身不确定）。"""
    settings = get_settings()
    if not settings.react_enabled or not settings.react_low_confidence_fallback:
        return False
    if intent_source == "rule":
        return False
    return confidence < settings.react_low_confidence_threshold


def should_use_react_tool_loop(
    intent_source: str,
    confidence: float,
    *,
    intent: str = "",
    query: str = "",
) -> bool:
    """
    工具意图是否走 ReAct 多轮。
    高置信度走 legacy 单轮；低置信度或指代性提问（缺诗题）走 ReAct。
    """
    settings = get_settings()
    if not settings.react_enabled or not settings.react_tool_loop_enabled:
        return False

    from app.agent.context_resolver import needs_poem_context

    if intent in ("tool_meter", "tool_lookup", "tool_allusion") and needs_poem_context(query):
        return True

    return confidence < settings.react_low_confidence_threshold


@traceable(run_type="chain", name="run_limited_react")
def run_limited_react(
    state: AgentState,
    *,
    max_steps: int | None = None,
    reason: str,
    intent_hint: str | None = None,
    include_rag_tool: bool = True,
) -> AgentState:
    """
    有限 ReAct：LLM 绑定工具 → 执行 → 观察 → 重复，直到无 tool_calls 或达 max_steps。
    不在此节点生成最终自然语言回答（由 stream_final_answer / generate_tool_summary 完成）。
    """
    settings = get_settings()
    steps_limit = max_steps if max_steps is not None else settings.react_max_steps
    filters = state.get("filters") or {}
    query = _last_user_text(state["messages"])
    intent = state.get("intent", "chat")
    poem_ctx = resolve_poem_context(state["messages"], query)
    log_route(
        "react_start",
        reason=reason,
        intent=intent,
        max_steps=steps_limit,
        include_rag_tool=include_rag_tool,
        poem_context=poem_ctx.get("title"),
        query=query,
    )

    tools, rag_budget = build_react_tools(
        filters=filters,
        include_rag_tool=include_rag_tool,
        rag_budget=_RagBudget(settings.react_rag_max_searches),
    )
    tool_map = {t.name: t for t in tools}
    llm = get_react_llm().bind_tools(tools)

    hint = intent_hint or REACT_AGENT_PROMPT
    ctx_hint = format_poem_context_hint(poem_ctx)
    system_parts = [SYSTEM_PROMPT, hint]
    if ctx_hint:
        system_parts.append(ctx_hint)
    react_messages: list[BaseMessage] = [
        SystemMessage(content="\n\n".join(system_parts)),
        *state["messages"][-6:],
        HumanMessage(content=f"用户问题：{query}"),
    ]

    react_steps = 0
    tool_call_rounds = 0

    for _ in range(steps_limit):
        resp = llm.invoke(
            react_messages,
            config=get_run_config(step="react_loop", reason=reason, round=react_steps),
        )
        if not isinstance(resp, AIMessage):
            resp = AIMessage(content=str(resp))
        react_messages.append(resp)
        react_steps += 1

        if not resp.tool_calls:
            break

        tool_call_rounds += 1
        tool_msgs = _execute_tool_calls(resp, tool_map)
        react_messages.extend(tool_msgs)

    tool_msgs = [m for m in react_messages if isinstance(m, ToolMessage)]
    tool_text = "\n\n---\n\n".join(
        getattr(m, "content", str(m)) for m in tool_msgs
    )
    rag_context = "\n\n---\n\n".join(rag_budget.contexts)
    source_refs = list(state.get("source_refs") or [])
    seen = {(s.get("title"), s.get("author")) for s in source_refs}
    for s in rag_budget.sources:
        key = (s.get("title"), s.get("author"))
        if key not in seen:
            source_refs.append(s)
            seen.add(key)

    update_run_metadata(
        react_reason=reason,
        react_steps=react_steps,
        react_tool_rounds=tool_call_rounds,
        react_rag_searches=settings.react_rag_max_searches - rag_budget.remaining,
        doc_count=len(rag_budget.sources),
    )
    tool_names = [
        tc.get("name") if isinstance(tc, dict) else tc.name
        for m in react_messages
        if isinstance(m, AIMessage) and m.tool_calls
        for tc in m.tool_calls
    ]
    log_route(
        "react_done",
        reason=reason,
        intent=intent,
        steps=react_steps,
        tool_rounds=tool_call_rounds,
        tools=",".join(tool_names) if tool_names else "none",
        rag_searches=settings.react_rag_max_searches - rag_budget.remaining,
        query=query,
    )

    return {
        **state,
        "messages": react_messages,
        "tool_result": tool_text,
        "rag_context": rag_context or state.get("rag_context", ""),
        "source_refs": source_refs,
        "react_steps": react_steps,
        "react_mode": True,
    }

"""LangGraph 工作流：意图识别 → RAG / 工具 / 复合问题 / 多轮记忆。"""
from __future__ import annotations

import operator
import time
from collections.abc import AsyncIterator
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from app.agent.checkpoint import get_checkpointer
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Send

from app.agent.compound_pipeline import (
    build_compound_prepared,
    build_compound_stream_messages,
    classify_sub_queries,
    collapse_same_intent_subqueries,
    decompose_query,
    execute_subtasks_parallel,
    merge_subtask_state,
    should_use_compound_pipeline,
    unique_sub_intents_for_display,
)
from app.agent.intent_classifier import classify_single_intent
from app.agent.intent_models import SubQueryIntent
from app.agent.llm import get_llm
from app.agent.prompts import (
    RAG_PROMPT,
    SYSTEM_PROMPT,
    structured_output_hint,
)
from app.agent.sources import build_sources_from_prepared
from app.agent.tools import AGENT_TOOLS
from app.config import get_settings
from app.observability.langsmith import get_run_config, traceable, update_run_metadata
from app.observability.tokens import usage_from_message
from app.rag.retriever import format_context, get_hybrid_retriever
from app.security.filter import strip_user_input

# ---------- State ----------


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str
    rag_context: str
    tool_result: str
    filters: dict
    source_refs: list[dict]
    sub_queries: NotRequired[list[dict]]
    is_compound: NotRequired[bool]
    primary_intent: NotRequired[str]
    original_query: NotRequired[str]
    sub_query: NotRequired[dict]
    completed_subtasks: NotRequired[Annotated[list[dict], operator.add]]


class PreparedAgent(TypedDict):
    state: AgentState
    intent: str
    mode: Literal["rag", "tool_summary", "chat", "compound_synthesis"]
    token_usage: NotRequired[int]
    sub_intents: NotRequired[list[dict]]
    is_compound: NotRequired[bool]


# ---------- Nodes ----------


@traceable(run_type="chain", name="classify_intent")
def classify_intent(state: AgentState) -> AgentState:
    """意图识别：规则优先，LLM 结构化兜底。"""
    last = _last_user_text(state)
    intent, intent_source, confidence = classify_single_intent(last)

    update_run_metadata(
        final_intent=intent,
        intent_source=intent_source,
        intent_confidence=confidence,
        rule_hit=intent_source == "rule",
    )
    return {
        **state,
        "intent": intent,
        "primary_intent": intent,
        "is_compound": False,
    }


@traceable(run_type="chain", name="decompose_node")
def decompose_node(state: AgentState) -> AgentState:
    """复合问题拆解节点。"""
    last = _last_user_text(state)
    decomposed = decompose_query(last)
    sub_queries = classify_sub_queries(decomposed)
    return {
        **state,
        "sub_queries": [s.model_dump() for s in sub_queries],
        "is_compound": decomposed.is_compound and len(sub_queries) > 1,
        "original_query": last,
        "completed_subtasks": [],
    }


def _sub_from_dict(data: dict) -> SubQueryIntent:
    return SubQueryIntent.model_validate(data)


@traceable(run_type="chain", name="execute_subtask_node")
def execute_subtask_node(state: AgentState) -> dict:
    """LangGraph Send 子节点：执行单个子任务。"""
    from app.agent.compound_pipeline import execute_subtask

    sub = _sub_from_dict(state["sub_query"])
    filters = state.get("filters") or {}
    prior = [m for m in state["messages"] if isinstance(m, HumanMessage)][:-1]
    prior_all = list(state["messages"][:-1]) if state.get("messages") else []
    executed = execute_subtask(
        sub,
        filters=filters,
        prior_messages=prior_all or prior,
    )
    return {"completed_subtasks": [executed.model_dump()]}


def merge_subtasks_node(state: AgentState) -> AgentState:
    """合并并行子任务结果。"""
    completed = state.get("completed_subtasks") or []
    sub_queries = [_sub_from_dict(s) for s in completed]
    if not sub_queries:
        raw = state.get("sub_queries") or []
        sub_queries = [_sub_from_dict(s) for s in raw]

    merged = merge_subtask_state(
        sub_queries,
        original_query=state.get("original_query") or _last_user_text(state),
        filters=state.get("filters") or {},
        prior_messages=list(state["messages"][:-1]),
    )
    return {**state, **merged}


def apply_single_sub_intent(state: AgentState) -> AgentState:
    """拆解后仅一条子任务：写入 intent 走单路径。"""
    subs = state.get("sub_queries") or []
    intent = subs[0].get("intent", "chat") if subs else state.get("intent", "chat")
    return {
        **state,
        "intent": intent,
        "primary_intent": intent,
        "is_compound": False,
    }


def continue_to_subtasks(state: AgentState) -> list[Send] | Literal["apply_single"]:
    subs = state.get("sub_queries") or []
    if state.get("is_compound") and len(subs) > 1:
        return [
            Send(
                "execute_subtask",
                {
                    "sub_query": sq,
                    "filters": state.get("filters") or {},
                    "messages": state["messages"],
                },
            )
            for sq in subs
        ]
    return "apply_single"


@traceable(run_type="retriever", name="retrieve_rag")
def retrieve_rag(state: AgentState) -> AgentState:
    query = _last_user_text(state)
    subs = state.get("sub_queries") or []
    if subs and len(subs) == 1:
        query = subs[0].get("text", query)
    filters = state.get("filters") or {}
    retriever = get_hybrid_retriever()
    docs = retriever.retrieve(
        query,
        author=filters.get("author"),
        dynasty=filters.get("dynasty"),
        genre=filters.get("genre"),
    )
    context = format_context(docs)
    source_refs = [
        {
            "title": d.metadata.get("title"),
            "author": d.metadata.get("author"),
            "snippet": d.page_content[:200],
            "source_file": d.metadata.get("source_file"),
        }
        for d in docs
    ]
    update_run_metadata(
        doc_count=len(docs),
        context_chars=len(context),
        query=query[:200],
        filters=filters or None,
    )
    return {**state, "rag_context": context, "source_refs": source_refs}


def generate_rag_answer(state: AgentState) -> AgentState:
    llm = get_llm()
    history = _format_history(state["messages"][:-1])
    prompt = RAG_PROMPT.format(
        context=state.get("rag_context") or "（无检索结果）",
        history=history or "（无）",
        question=_last_user_text(state),
    )
    resp = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT + structured_output_hint("rag")),
            HumanMessage(content=prompt),
        ]
    )
    return {
        **state,
        "messages": [AIMessage(content=resp.content)],
    }


@traceable(run_type="chain", name="prepare_tool_call")
def prepare_tool_call(state: AgentState) -> AgentState:
    """根据意图构造带工具调用的消息。"""
    llm = get_llm().bind_tools(AGENT_TOOLS)
    intent = state.get("intent", "chat")
    subs = state.get("sub_queries") or []
    if subs and len(subs) == 1:
        intent = subs[0].get("intent", intent)
        state = {**state, "intent": intent}
    hint = {
        "tool_author": "请使用 author_query 工具查询作者信息。",
        "tool_meter": "请使用 meter_analysis 工具分析格律，从用户输入提取诗题。",
        "tool_compare": "请使用 style_compare 工具对比诗人风格。",
        "tool_lookup": "请使用 poem_lookup 工具查找诗词原文、注释或译文。",
        "tool_theme": "请使用 theme_recommend 工具按主题推荐诗词。",
        "tool_allusion": "请使用 allusion_explain 工具解释典故或字词含义。",
        "tool_writing": "请使用 writing_assistant 工具获取创作指南，再据此为用户创作示例。若用户提供了画面描述，请以画面意象为主题创作。",
    }.get(intent, "请根据问题选择合适的工具。")

    resp = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            *state["messages"][-6:],
            HumanMessage(content=hint + "\n用户问题：" + _last_user_text(state)),
        ],
        config=get_run_config(step="prepare_tool_call", intent=intent),
    )
    tool_calls = []
    if hasattr(resp, "tool_calls") and resp.tool_calls:
        tool_calls = [
            tc.get("name") if isinstance(tc, dict) else tc.name
            for tc in resp.tool_calls
        ]
    update_run_metadata(intent=intent, tool_calls=tool_calls or None)
    return {**state, "messages": [resp]}


def _tool_summary_user_content(intent: str, tool_text: str) -> str:
    base = f"工具返回结果：\n{tool_text}\n\n请整理为中文回答，并引用工具中的事实。"
    if intent == "tool_writing":
        return (
            f"{base}\n\n"
            "这是诗词创作任务：须按工具 rules 与 output_requirements 先写出完整诗作"
            "（每句一行），再在 JSON 中用 lines 数组列出全部句子。"
        )
    return base


def generate_tool_summary(state: AgentState) -> AgentState:
    """工具执行后，由 LLM 整理为自然语言回答。"""
    llm = get_llm()
    intent = state.get("intent", "chat")
    tool_msgs = [m for m in state["messages"] if m.type == "tool"]
    tool_text = "\n".join(getattr(m, "content", str(m)) for m in tool_msgs)

    resp = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT + structured_output_hint(intent)),
            HumanMessage(content=_tool_summary_user_content(intent, tool_text)),
        ]
    )
    return {
        **state,
        "messages": [AIMessage(content=resp.content)],
        "tool_result": tool_text,
    }


def general_chat(state: AgentState) -> AgentState:
    llm = get_llm()
    resp = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), *state["messages"][-8:]]
    )
    return {**state, "messages": [AIMessage(content=resp.content)]}


# ---------- Routing ----------


def route_by_intent(state: AgentState) -> Literal["retrieve", "tools", "chat"]:
    intent = state.get("intent", "chat")
    if intent == "rag":
        return "retrieve"
    if intent.startswith("tool_"):
        return "tools"
    return "chat"


def should_continue_tools(state: AgentState) -> Literal["tools", "summarize"]:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "summarize"


# ---------- Graph build ----------

_tool_node = ToolNode(AGENT_TOOLS)


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("classify", classify_intent)
    g.add_node("decompose", decompose_node)
    g.add_node("apply_single", apply_single_sub_intent)
    g.add_node("execute_subtask", execute_subtask_node)
    g.add_node("merge_subtasks", merge_subtasks_node)
    g.add_node("retrieve", retrieve_rag)
    g.add_node("generate_rag", generate_rag_answer)
    g.add_node("prepare_tools", prepare_tool_call)
    g.add_node("tools", _tool_node)
    g.add_node("summarize_tools", generate_tool_summary)
    g.add_node("chat", general_chat)

    def _entry_route(state: AgentState) -> Literal["decompose", "classify"]:
        if get_settings().compound_intent_enabled:
            return "decompose"
        return "classify"

    g.set_conditional_entry_point(
        _entry_route,
        {"decompose": "decompose", "classify": "classify"},
    )

    g.add_conditional_edges(
        "decompose",
        continue_to_subtasks,
        {"apply_single": "apply_single", "execute_subtask": "execute_subtask"},
    )
    g.add_edge("execute_subtask", "merge_subtasks")
    g.add_edge("merge_subtasks", END)

    g.add_conditional_edges(
        "apply_single",
        route_by_intent,
        {
            "retrieve": "retrieve",
            "tools": "prepare_tools",
            "chat": "chat",
        },
    )

    g.add_conditional_edges(
        "classify",
        route_by_intent,
        {
            "retrieve": "retrieve",
            "tools": "prepare_tools",
            "chat": "chat",
        },
    )
    g.add_edge("retrieve", "generate_rag")
    g.add_edge("generate_rag", END)
    g.add_edge("chat", END)

    g.add_conditional_edges(
        "prepare_tools",
        should_continue_tools,
        {"tools": "tools", "summarize": "summarize_tools"},
    )
    g.add_edge("tools", "summarize_tools")
    g.add_edge("summarize_tools", END)

    return g.compile(checkpointer=get_checkpointer())


_graph = None


def get_agent_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def _initial_state(
    message: str,
    filters: dict | None,
    prior_messages: list[BaseMessage] | None = None,
) -> AgentState:
    msgs = list(prior_messages or [])
    msgs.append(HumanMessage(content=message))
    return {
        "messages": msgs,
        "intent": "",
        "rag_context": "",
        "tool_result": "",
        "filters": filters or {},
        "source_refs": [],
        "sub_queries": [],
        "is_compound": False,
        "primary_intent": "",
        "original_query": "",
        "completed_subtasks": [],
    }


def _prior_messages(thread_id: str) -> list[BaseMessage]:
    graph = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snap = graph.get_state(config)
    if snap and snap.values:
        return list(snap.values.get("messages", []))
    return []


@traceable(run_type="tool", name="run_tools")
def _run_tools(state: AgentState) -> list[ToolMessage]:
    """在 graph 外直接执行 tool_calls，避免 ToolNode 依赖 runtime config。"""
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return []

    tool_map = {t.name: t for t in AGENT_TOOLS}
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
                content = f"工具执行失败: {e}"
                tool_results_meta.append({"name": name, "success": False, "error": str(e)})

        results.append(ToolMessage(content=content, tool_call_id=tool_call_id))

    update_run_metadata(tool_results=tool_results_meta)
    return results


def _sub_intents_payload(state: AgentState, intent: str) -> list[dict]:
    raw = state.get("sub_queries") or []
    if raw:
        subs = [
            SubQueryIntent.model_validate(s) if isinstance(s, dict) else s
            for s in raw
        ]
        return unique_sub_intents_for_display(subs)
    last = _last_user_text(state)
    return [{"text": last, "intent": intent}] if intent else []


@traceable(run_type="chain", name="prepare_agent")
def prepare_agent(
    message: str,
    thread_id: str = "default",
    filters: dict | None = None,
) -> PreparedAgent:
    """运行意图识别与检索/工具阶段，返回待流式生成的状态。"""
    prior = _prior_messages(thread_id)
    if get_settings().compound_intent_enabled:
        return _prepare_compound_agent(message, thread_id, filters, prior)

    state = _initial_state(message, filters, prior)
    return _prepare_single_agent(state)


def _prepare_single_agent(state: AgentState) -> PreparedAgent:
    if not state.get("intent"):
        state = classify_intent(state)
    else:
        state = {
            **state,
            "primary_intent": state.get("primary_intent") or state["intent"],
            "is_compound": False,
        }
    intent = state.get("intent", "chat")

    if intent == "rag":
        state = retrieve_rag(state)
        mode: Literal["rag", "tool_summary", "chat", "compound_synthesis"] = "rag"
    elif intent.startswith("tool_"):
        state = prepare_tool_call(state)
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            tool_msgs = _run_tools(state)
            state = {**state, "messages": state["messages"] + tool_msgs}
        tool_msgs = [m for m in state["messages"] if m.type == "tool"]
        state["tool_result"] = "\n".join(
            getattr(m, "content", str(m)) for m in tool_msgs
        )
        mode = "tool_summary"
    else:
        mode = "chat"

    update_run_metadata(intent=intent, mode=mode, filters=state.get("filters") or None)
    sub_intents = _sub_intents_payload(state, intent)
    return {
        "state": state,
        "intent": intent,
        "mode": mode,
        "is_compound": len(sub_intents) > 1,
        "sub_intents": sub_intents,
    }


def _prepare_compound_agent(
    message: str,
    thread_id: str,
    filters: dict | None,
    prior: list[BaseMessage],
) -> PreparedAgent:
    decomposed = decompose_query(message)
    sub_queries = classify_sub_queries(decomposed)
    sub_queries = collapse_same_intent_subqueries(sub_queries, message)

    if not should_use_compound_pipeline(sub_queries):
        state = _initial_state(message, filters, prior)
        if sub_queries:
            sq = sub_queries[0]
            state = {
                **state,
                "intent": sq.intent,
                "primary_intent": sq.intent,
                "sub_queries": [sq.model_dump()],
            }
        prepared = _prepare_single_agent(state)
        prepared["sub_intents"] = unique_sub_intents_for_display(sub_queries)
        prepared["is_compound"] = False
        return prepared

    executed = execute_subtasks_parallel(
        sub_queries,
        filters=filters or {},
        prior_messages=prior,
    )
    merged_state = merge_subtask_state(
        executed,
        original_query=message,
        filters=filters or {},
        prior_messages=prior,
    )
    prepared = build_compound_prepared(message, executed, merged_state)
    update_run_metadata(
        intent=prepared["intent"],
        mode="compound_synthesis",
        filters=filters or None,
        is_compound=True,
        sub_query_count=len(executed),
    )
    return prepared


def _build_stream_messages(prepared: PreparedAgent) -> list[BaseMessage]:
    state = prepared["state"]
    mode = prepared["mode"]

    if mode == "rag":
        history = _format_history(state["messages"][:-1])
        prompt = RAG_PROMPT.format(
            context=state.get("rag_context") or "（无检索结果）",
            history=history or "（无）",
            question=_last_user_text(state),
        )
        return [
            SystemMessage(content=SYSTEM_PROMPT + structured_output_hint("rag")),
            HumanMessage(content=prompt),
        ]

    if mode == "compound_synthesis":
        sub_queries = [
            SubQueryIntent.model_validate(s)
            for s in (state.get("sub_queries") or [])
        ]
        original = state.get("original_query") or _last_user_text(state)
        return build_compound_stream_messages(original, sub_queries)

    if mode == "tool_summary":
        intent = prepared.get("intent", "chat")
        tool_text = state.get("tool_result") or ""
        return [
            SystemMessage(content=SYSTEM_PROMPT + structured_output_hint(intent)),
            HumanMessage(content=_tool_summary_user_content(intent, tool_text)),
        ]

    return [SystemMessage(content=SYSTEM_PROMPT), *state["messages"][-8:]]


@traceable(run_type="llm", name="stream_final_answer")
async def stream_final_answer(prepared: PreparedAgent) -> AsyncIterator[str]:
    """流式输出最终 LLM 回答。"""
    llm = get_llm()
    messages = _build_stream_messages(prepared)
    mode = prepared["mode"]
    config = get_run_config(step="stream_final_answer", mode=mode)
    start = time.perf_counter()
    first_token = True
    token_usage = 0

    async for chunk in llm.astream(messages, config=config):
        token_usage = max(token_usage, usage_from_message(chunk))
        content = chunk.content
        if first_token:
            ttft_ms = round((time.perf_counter() - start) * 1000, 2)
            update_run_metadata(ttft_ms=ttft_ms, mode=mode)
            first_token = False
        if isinstance(content, str) and content:
            yield content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str) and part:
                    yield part
                elif isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    if text:
                        yield text

    if token_usage:
        prepared["token_usage"] = token_usage
        update_run_metadata(token_usage=token_usage, mode=mode)


@traceable(run_type="llm", name="collect_stream")
def _collect_stream(prepared: PreparedAgent) -> tuple[str, int]:
    llm = get_llm()
    messages = _build_stream_messages(prepared)
    mode = prepared["mode"]
    resp = llm.invoke(
        messages,
        config=get_run_config(step="collect_stream", mode=mode),
    )
    tokens = usage_from_message(resp)
    if tokens:
        prepared["token_usage"] = tokens
    update_run_metadata(mode=mode, token_usage=tokens)
    content = resp.content if hasattr(resp, "content") else str(resp)
    return content, tokens


def commit_agent_state(
    thread_id: str,
    user_message: str,
    assistant_content: str,
    prepared: PreparedAgent,
) -> None:
    """将完整一轮对话写入 LangGraph checkpoint。"""
    graph = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}
    state = prepared["state"]
    graph.update_state(
        config,
        {
            "messages": [
                HumanMessage(content=user_message),
                AIMessage(content=assistant_content),
            ],
            "intent": prepared.get("intent") or prepared["state"].get("primary_intent", ""),
            "rag_context": state.get("rag_context", ""),
            "tool_result": state.get("tool_result", ""),
            "filters": state.get("filters") or {},
            "source_refs": state.get("source_refs") or [],
            "sub_queries": state.get("sub_queries") or [],
            "is_compound": state.get("is_compound", False),
            "primary_intent": state.get("primary_intent", prepared.get("intent", "")),
            "original_query": state.get("original_query", user_message),
        },
    )


def clear_thread_checkpoint(thread_id: str) -> None:
    """同步包装：清除指定 thread 的 checkpoint。"""
    import asyncio

    from app.agent.checkpoint import clear_thread_checkpoint as _clear

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_clear(thread_id))
        else:
            loop.run_until_complete(_clear(thread_id))
    except RuntimeError:
        asyncio.run(_clear(thread_id))


def run_agent(
    message: str,
    thread_id: str = "default",
    filters: dict | None = None,
) -> dict:
    prepared = prepare_agent(message, thread_id=thread_id, filters=filters)
    answer, tokens_used = _collect_stream(prepared)
    commit_agent_state(thread_id, message, answer, prepared)
    state = prepared["state"]
    return {
        "answer": answer,
        "intent": prepared["intent"],
        "rag_context": state.get("rag_context", ""),
        "tool_result": state.get("tool_result", ""),
        "sources": build_sources_from_prepared(prepared),
        "tokens_used": tokens_used,
    }


# ---------- helpers ----------


def _last_user_text(state: AgentState) -> str:
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            raw = m.content if isinstance(m.content, str) else str(m.content)
            return strip_user_input(raw)
    return ""


def _format_history(messages: list[BaseMessage]) -> str:
    lines = []
    for m in messages[-6:]:
        role = "用户" if isinstance(m, HumanMessage) else "助手"
        content = m.content if isinstance(m.content, str) else str(m.content)
        lines.append(f"{role}：{content[:300]}")
    return "\n".join(lines)

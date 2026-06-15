"""LangGraph 工作流：意图识别 → RAG / 工具 / 多轮记忆。"""
from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.agent.llm import get_llm
from app.agent.prompts import (
    INTENT_CLASSIFIER_PROMPT,
    RAG_PROMPT,
    STRUCTURED_OUTPUT_HINT,
    SYSTEM_PROMPT,
)
from app.agent.sources import build_sources_from_prepared
from app.agent.tools import AGENT_TOOLS
from app.observability.langsmith import get_run_config, traceable, update_run_metadata
from app.rag.retriever import format_context, get_hybrid_retriever

# ---------- State ----------


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str
    rag_context: str
    tool_result: str
    filters: dict
    source_refs: list[dict]


class PreparedAgent(TypedDict):
    state: AgentState
    intent: str
    mode: Literal["rag", "tool_summary", "chat"]


# ---------- Nodes ----------


@traceable(run_type="chain", name="classify_intent")
def classify_intent(state: AgentState) -> AgentState:
    """意图识别：规则优先，LLM 兜底。"""
    last = _last_user_text(state)
    rule_intent = _rule_based_intent(last)
    intent = rule_intent
    intent_source = "rule" if rule_intent != "chat" else "llm"

    if rule_intent == "chat":
        llm = get_llm()
        resp = llm.invoke(
            INTENT_CLASSIFIER_PROMPT.format(query=last),
            config=get_run_config(step="intent_classifier"),
        )
        raw = resp.content.strip().lower() if hasattr(resp, "content") else str(resp)
        for key in (
            "rag",
            "tool_author",
            "tool_meter",
            "tool_compare",
            "tool_lookup",
            "tool_theme",
            "tool_allusion",
            "tool_writing",
            "chat",
        ):
            if key in raw:
                intent = key
                break

    update_run_metadata(
        final_intent=intent,
        intent_source=intent_source,
        rule_hit=rule_intent != "chat",
    )
    return {**state, "intent": intent}


def _rule_based_intent(text: str) -> str:
    if any(k in text for k in ("写一首", "创作", "对联", "藏头", "填词", "仿写", "帮我写")):
        return "tool_writing"
    if any(k in text for k in ("什么意思", "指什么", "典故", "含义", "是指")) and any(
        k in text for k in ("中的", "里的", "「", "『", "这句", "字")
    ):
        return "tool_allusion"
    if any(k in text for k in ("推荐", "有哪些", "关于")) and any(
        k in text
        for k in ("诗", "词", "主题", "思乡", "送别", "怀古", "春天", "秋天", "爱情")
    ):
        return "tool_theme"
    if any(k in text for k in ("查找", "原文", "注释", "译文", "全文", "哪首诗")) or (
        "《" in text and "》" in text
        and any(k in text for k in ("原文", "注释", "译文", "查找", "全文"))
    ):
        return "tool_lookup"
    if any(k in text for k in ("生平", "介绍", "是谁", "代表作", "诗人")) and any(
        a in text for a in ("李白", "杜甫", "苏轼", "李清照", "作者")
    ):
        if "对比" not in text and "区别" not in text:
            return "tool_author"
    if any(k in text for k in ("格律", "平仄", "押韵", "体裁", "分析")):
        if "赏析" not in text and "鉴赏" not in text:
            return "tool_meter"
    if any(k in text for k in ("对比", "区别", "vs", "和")) and any(
        a in text for a in ("李白", "杜甫", "苏轼", "李清照")
    ):
        return "tool_compare"
    if any(k in text for k in ("赏析", "鉴赏", "欣赏", "含义", "主旨")):
        return "rag"
    if re.search(r"《.+?》", text) or any(
        t in text for t in ("静夜思", "登高", "念奴娇", "赤壁")
    ):
        if "原文" not in text and "注释" not in text and "查找" not in text:
            return "rag"
    return "chat"


@traceable(run_type="retriever", name="retrieve_rag")
def retrieve_rag(state: AgentState) -> AgentState:
    query = _last_user_text(state)
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
            SystemMessage(content=SYSTEM_PROMPT + STRUCTURED_OUTPUT_HINT),
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
    hint = {
        "tool_author": "请使用 author_query 工具查询作者信息。",
        "tool_meter": "请使用 meter_analysis 工具分析格律，从用户输入提取诗题。",
        "tool_compare": "请使用 style_compare 工具对比诗人风格。",
        "tool_lookup": "请使用 poem_lookup 工具查找诗词原文、注释或译文。",
        "tool_theme": "请使用 theme_recommend 工具按主题推荐诗词。",
        "tool_allusion": "请使用 allusion_explain 工具解释典故或字词含义。",
        "tool_writing": "请使用 writing_assistant 工具获取创作指南，再据此为用户创作示例。",
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


def generate_tool_summary(state: AgentState) -> AgentState:
    """工具执行后，由 LLM 整理为自然语言回答。"""
    llm = get_llm()
    tool_msgs = [m for m in state["messages"] if m.type == "tool"]
    tool_text = "\n".join(getattr(m, "content", str(m)) for m in tool_msgs)

    resp = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT + STRUCTURED_OUTPUT_HINT),
            HumanMessage(
                content=f"工具返回结果：\n{tool_text}\n\n请整理为中文回答，并引用工具中的事实。"
            ),
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
_memory = MemorySaver()


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("classify", classify_intent)
    g.add_node("retrieve", retrieve_rag)
    g.add_node("generate_rag", generate_rag_answer)
    g.add_node("prepare_tools", prepare_tool_call)
    g.add_node("tools", _tool_node)
    g.add_node("summarize_tools", generate_tool_summary)
    g.add_node("chat", general_chat)

    g.set_entry_point("classify")
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

    return g.compile(checkpointer=_memory)


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


@traceable(run_type="chain", name="prepare_agent")
def prepare_agent(
    message: str,
    thread_id: str = "default",
    filters: dict | None = None,
) -> PreparedAgent:
    """运行意图识别与检索/工具阶段，返回待流式生成的状态。"""
    prior = _prior_messages(thread_id)
    state = _initial_state(message, filters, prior)
    state = classify_intent(state)
    intent = state.get("intent", "chat")

    if intent == "rag":
        state = retrieve_rag(state)
        mode: Literal["rag", "tool_summary", "chat"] = "rag"
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

    update_run_metadata(intent=intent, mode=mode, filters=filters or None)
    return {"state": state, "intent": intent, "mode": mode}


def _build_stream_messages(prepared: PreparedAgent) -> list[BaseMessage]:
    state = prepared["state"]
    mode = prepared["mode"]
    llm = get_llm()

    if mode == "rag":
        history = _format_history(state["messages"][:-1])
        prompt = RAG_PROMPT.format(
            context=state.get("rag_context") or "（无检索结果）",
            history=history or "（无）",
            question=_last_user_text(state),
        )
        return [
            SystemMessage(content=SYSTEM_PROMPT + STRUCTURED_OUTPUT_HINT),
            HumanMessage(content=prompt),
        ]

    if mode == "tool_summary":
        tool_text = state.get("tool_result") or ""
        return [
            SystemMessage(content=SYSTEM_PROMPT + STRUCTURED_OUTPUT_HINT),
            HumanMessage(
                content=f"工具返回结果：\n{tool_text}\n\n请整理为中文回答，并引用工具中的事实。"
            ),
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

    async for chunk in llm.astream(messages, config=config):
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


@traceable(run_type="llm", name="collect_stream")
def _collect_stream(prepared: PreparedAgent) -> str:
    llm = get_llm()
    messages = _build_stream_messages(prepared)
    mode = prepared["mode"]
    resp = llm.invoke(
        messages,
        config=get_run_config(step="collect_stream", mode=mode),
    )
    update_run_metadata(mode=mode)
    return resp.content if hasattr(resp, "content") else str(resp)


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
            "intent": prepared["intent"],
            "rag_context": state.get("rag_context", ""),
            "tool_result": state.get("tool_result", ""),
            "filters": state.get("filters") or {},
            "source_refs": state.get("source_refs") or [],
        },
    )


def clear_thread_checkpoint(thread_id: str) -> None:
    """清除指定 thread 的内存 checkpoint。"""
    checkpointer = get_agent_graph().checkpointer
    if not hasattr(checkpointer, "storage"):
        return
    keys = [k for k in checkpointer.storage if k[0] == thread_id]
    for key in keys:
        del checkpointer.storage[key]


def run_agent(
    message: str,
    thread_id: str = "default",
    filters: dict | None = None,
) -> dict:
    prepared = prepare_agent(message, thread_id=thread_id, filters=filters)
    answer = _collect_stream(prepared)
    commit_agent_state(thread_id, message, answer, prepared)
    state = prepared["state"]
    return {
        "answer": answer,
        "intent": prepared["intent"],
        "rag_context": state.get("rag_context", ""),
        "tool_result": state.get("tool_result", ""),
        "sources": build_sources_from_prepared(prepared),
    }


# ---------- helpers ----------


def _last_user_text(state: AgentState) -> str:
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""


def _format_history(messages: list[BaseMessage]) -> str:
    lines = []
    for m in messages[-6:]:
        role = "用户" if isinstance(m, HumanMessage) else "助手"
        content = m.content if isinstance(m.content, str) else str(m.content)
        lines.append(f"{role}：{content[:300]}")
    return "\n".join(lines)

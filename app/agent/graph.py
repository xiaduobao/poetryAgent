"""LangGraph 工作流：意图识别 → RAG / 工具 / 多轮记忆。"""
from __future__ import annotations

import json
import re
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
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
from app.agent.tools import AGENT_TOOLS
from app.rag.retriever import format_context, get_hybrid_retriever

# ---------- State ----------


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str
    rag_context: str
    tool_result: str
    filters: dict


# ---------- Nodes ----------


def classify_intent(state: AgentState) -> AgentState:
    """意图识别：规则优先，LLM 兜底。"""
    last = _last_user_text(state)
    intent = _rule_based_intent(last)
    if intent == "chat":
        llm = get_llm()
        resp = llm.invoke(
            INTENT_CLASSIFIER_PROMPT.format(query=last)
        )
        raw = resp.content.strip().lower() if hasattr(resp, "content") else str(resp)
        for key in ("rag", "tool_author", "tool_meter", "tool_compare", "chat"):
            if key in raw:
                intent = key
                break
    return {**state, "intent": intent}


def _rule_based_intent(text: str) -> str:
    if any(k in text for k in ("生平", "介绍", "是谁", "代表作", "诗人")) and any(
        a in text for a in ("李白", "杜甫", "苏轼", "李清照", "作者")
    ):
        if "对比" not in text and "区别" not in text:
            return "tool_author"
    if any(k in text for k in ("格律", "平仄", "押韵", "体裁", "分析")):
        return "tool_meter"
    if any(k in text for k in ("对比", "区别", "vs", "和")) and any(
        a in text for a in ("李白", "杜甫", "苏轼", "李清照")
    ):
        return "tool_compare"
    if any(k in text for k in ("赏析", "鉴赏", "欣赏", "赏析", "含义", "主旨")):
        return "rag"
    if re.search(r"《.+?》", text) or any(
        t in text for t in ("静夜思", "登高", "念奴娇", "赤壁")
    ):
        return "rag"
    return "chat"


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
    return {**state, "rag_context": format_context(docs)}


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


def prepare_tool_call(state: AgentState) -> AgentState:
    """根据意图构造带工具调用的消息。"""
    llm = get_llm().bind_tools(AGENT_TOOLS)
    intent = state.get("intent", "chat")
    hint = {
        "tool_author": "请使用 author_query 工具查询作者信息。",
        "tool_meter": "请使用 meter_analysis 工具分析格律，从用户输入提取诗题。",
        "tool_compare": "请使用 style_compare 工具对比诗人风格。",
    }.get(intent, "请根据问题选择合适的工具。")

    resp = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            *state["messages"][-6:],
            HumanMessage(content=hint + "\n用户问题：" + _last_user_text(state)),
        ]
    )
    return {**state, "messages": [resp]}


def generate_tool_summary(state: AgentState) -> AgentState:
    """工具执行后，由 LLM 整理为自然语言回答。"""
    llm = get_llm()
    last_ai = state["messages"][-1]
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


def run_agent(
    message: str,
    thread_id: str = "default",
    filters: dict | None = None,
) -> dict:
    graph = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}
    initial: AgentState = {
        "messages": [HumanMessage(content=message)],
        "intent": "",
        "rag_context": "",
        "tool_result": "",
        "filters": filters or {},
    }
    result = graph.invoke(initial, config)
    last_ai = next(
        (m for m in reversed(result["messages"]) if isinstance(m, AIMessage)),
        None,
    )
    return {
        "answer": last_ai.content if last_ai else "",
        "intent": result.get("intent", ""),
        "rag_context": result.get("rag_context", ""),
        "tool_result": result.get("tool_result", ""),
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

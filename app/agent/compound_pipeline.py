"""复合问题：拆解、子任务执行、结果合并。"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agent.intent_classifier import classify_single_intent
from app.agent.intent_models import DecomposeResult, DecomposedSubQuery, SubQueryIntent, VALID_INTENTS
from app.agent.llm import get_llm
from app.agent.prompts import COMPOUND_SYNTHESIS_PROMPT, QUERY_DECOMPOSE_PROMPT, SYSTEM_PROMPT, structured_output_hint
from app.agent.route_log import log_route
from app.observability.langsmith import get_run_config, traceable, update_run_metadata
from app.security.filter import strip_user_input

if TYPE_CHECKING:
    from app.agent.graph import AgentState, PreparedAgent

logger = logging.getLogger(__name__)

_COMPOUND_CONNECTORS = ("并", "还有", "另外", "同时", "以及", "且", "再", "顺便")


def _parse_decompose_json(raw: str) -> DecomposeResult | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        sub_queries = []
        for sq in data.get("sub_queries") or []:
            intent = sq.get("suggested_intent", "chat")
            if intent not in VALID_INTENTS:
                intent = "chat"
            sub_queries.append(
                DecomposedSubQuery(
                    text=str(sq.get("text", "")).strip(),
                    suggested_intent=intent,  # type: ignore[arg-type]
                    confidence=float(sq.get("confidence", 0.8)),
                )
            )
        if not sub_queries:
            return None
        return DecomposeResult(
            is_compound=bool(data.get("is_compound", len(sub_queries) > 1)),
            confidence=float(data.get("confidence", 0.8)),
            sub_queries=sub_queries,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _heuristic_decompose(text: str) -> DecomposeResult:
    clean = strip_user_input(text)
    if not any(c in clean for c in _COMPOUND_CONNECTORS):
        intent, _, conf = classify_single_intent(clean)
        return DecomposeResult(
            is_compound=False,
            confidence=conf,
            sub_queries=[
                DecomposedSubQuery(text=clean, suggested_intent=intent, confidence=conf)  # type: ignore[arg-type]
            ],
        )

    parts = re.split(r"[，,；;]?(?:并|还有|另外|同时|以及|且|再|顺便)", clean)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 2:
        intent, _, conf = classify_single_intent(clean)
        return DecomposeResult(
            is_compound=False,
            confidence=conf,
            sub_queries=[
                DecomposedSubQuery(text=clean, suggested_intent=intent, confidence=conf)  # type: ignore[arg-type]
            ],
        )

    sub_queries: list[DecomposedSubQuery] = []
    for part in parts:
        intent, _, conf = classify_single_intent(part)
        sub_queries.append(
            DecomposedSubQuery(text=part, suggested_intent=intent, confidence=conf)  # type: ignore[arg-type]
        )
    return DecomposeResult(is_compound=True, confidence=0.7, sub_queries=sub_queries)


@traceable(run_type="chain", name="decompose_query")
def decompose_query(text: str) -> DecomposeResult:
    clean = strip_user_input(text)
    if not clean:
        return DecomposeResult(
            is_compound=False,
            confidence=1.0,
            sub_queries=[DecomposedSubQuery(text="", suggested_intent="chat")],
        )

    start = time.perf_counter()
    llm = get_llm()
    prompt = QUERY_DECOMPOSE_PROMPT.format(query=clean)
    result: DecomposeResult | None = None
    decompose_source = "unknown"

    try:
        structured = llm.with_structured_output(DecomposeResult)
        out = structured.invoke(prompt, config=get_run_config(step="decompose_query"))
        if isinstance(out, DecomposeResult) and out.sub_queries:
            result = out
            decompose_source = "structured"
    except Exception as e:
        logger.debug("structured decompose failed: %s", e)

    if result is None:
        resp = llm.invoke(prompt, config=get_run_config(step="decompose_query"))
        raw = resp.content.strip() if hasattr(resp, "content") else str(resp)
        result = _parse_decompose_json(raw)
        if result is not None:
            decompose_source = "json"

    if result is None or not result.sub_queries:
        result = _heuristic_decompose(clean)
        decompose_source = "heuristic"

    if result.confidence < 0.6 or (result.is_compound and len(result.sub_queries) == 1):
        intent, _, conf = classify_single_intent(clean)
        result = DecomposeResult(
            is_compound=False,
            confidence=conf,
            sub_queries=[
                DecomposedSubQuery(text=clean, suggested_intent=intent, confidence=conf)  # type: ignore[arg-type]
            ],
        )
        decompose_source = "single_fallback"

    decompose_ms = round((time.perf_counter() - start) * 1000, 2)
    sub_summary = "; ".join(
        f"{sq.text[:40]}→{sq.suggested_intent}" for sq in result.sub_queries[:4]
    )
    log_route(
        "decompose",
        source=decompose_source,
        is_compound=result.is_compound,
        sub_count=len(result.sub_queries),
        confidence=result.confidence,
        ms=decompose_ms,
        subs=sub_summary,
        query=clean,
    )
    update_run_metadata(
        is_compound=result.is_compound,
        sub_query_count=len(result.sub_queries),
        decompose_ms=decompose_ms,
        decompose_confidence=result.confidence,
    )
    return result


def classify_sub_queries(
    decomposed: DecomposeResult,
    *,
    messages: list[BaseMessage] | None = None,
) -> list[SubQueryIntent]:
    sub_queries: list[SubQueryIntent] = []
    for i, sq in enumerate(decomposed.sub_queries):
        intent, source, confidence = classify_single_intent(
            sq.text,
            suggested_intent=sq.suggested_intent,
            suggested_confidence=sq.confidence,
            messages=messages,
        )
        sub_queries.append(
            SubQueryIntent(
                id=f"q{i + 1}",
                text=sq.text,
                intent=intent,
                intent_source=source,
                confidence=confidence,
            )
        )
    sub_summary = "; ".join(
        f"{s.id}:{s.intent}({s.intent_source},{s.confidence:.2f})" for s in sub_queries
    )
    log_route("sub_intents", count=len(sub_queries), subs=sub_summary)
    return sub_queries


def collapse_same_intent_subqueries(
    sub_queries: list[SubQueryIntent],
    original: str,
) -> list[SubQueryIntent]:
    """拆解过细且意图相同时（如李杜对比拆成 3 段），合并为单任务。"""
    if len(sub_queries) <= 1:
        return sub_queries
    intents = {s.intent for s in sub_queries}
    if len(intents) > 1:
        return sub_queries
    best = max(sub_queries, key=lambda s: s.confidence)
    clean = strip_user_input(original)
    return [
        SubQueryIntent(
            id="q1",
            text=clean,
            intent=best.intent,
            intent_source=best.intent_source,
            confidence=best.confidence,
        )
    ]


def should_use_compound_pipeline(sub_queries: list[SubQueryIntent]) -> bool:
    """仅当存在多种不同意图时才走复合并行路径。"""
    if len(sub_queries) <= 1:
        return False
    return len({s.intent for s in sub_queries}) > 1


def unique_sub_intents_for_display(sub_queries: list[SubQueryIntent]) -> list[dict]:
    """展示用：每种意图只保留一个标签。"""
    seen: set[str] = set()
    out: list[dict] = []
    for s in sub_queries:
        if s.intent in seen:
            continue
        seen.add(s.intent)
        out.append({"text": s.text, "intent": s.intent})
    return out


def _retrieve_for_query(query: str, filters: dict) -> tuple[str, list[dict]]:
    from app.rag.retriever import format_context, get_hybrid_retriever

    retriever = get_hybrid_retriever()
    docs = retriever.retrieve(
        query,
        author=filters.get("author"),
        dynasty=filters.get("dynasty"),
        genre=filters.get("genre"),
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
    return context, sources


def _run_tool_for_subtask(
    sub: SubQueryIntent,
    prior_messages: list[BaseMessage],
) -> str:
    from app.agent.context_resolver import format_poem_context_hint, resolve_poem_context
    from app.agent.graph import _run_tools
    from app.agent.react_loop import INTENT_TOOL_HINTS
    from app.agent.tools import AGENT_TOOLS

    llm = get_llm().bind_tools(AGENT_TOOLS)
    hint = INTENT_TOOL_HINTS.get(sub.intent, "请根据问题选择合适的工具。")
    poem_ctx = resolve_poem_context([*prior_messages, HumanMessage(content=sub.text)], sub.text)
    ctx_hint = format_poem_context_hint(poem_ctx)
    user_block = f"{hint}\n用户问题：{sub.text}"
    if ctx_hint:
        user_block = f"{ctx_hint}\n\n{user_block}"

    resp = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            *prior_messages[-6:],
            HumanMessage(content=user_block),
        ],
        config=get_run_config(step="prepare_tool_call", intent=sub.intent),
    )
    if not isinstance(resp, AIMessage) or not resp.tool_calls:
        return ""

    state: dict[str, Any] = {"messages": [resp]}
    tool_msgs = _run_tools(state)  # type: ignore[arg-type]
    return "\n".join(getattr(m, "content", str(m)) for m in tool_msgs)


@traceable(run_type="chain", name="execute_subtask")
def execute_subtask(
    sub: SubQueryIntent,
    *,
    filters: dict,
    prior_messages: list[BaseMessage],
    rag_cache: dict[str, tuple[str, list[dict]]] | None = None,
) -> SubQueryIntent:
    if sub.intent == "rag":
        cache = rag_cache if rag_cache is not None else {}
        key = sub.text.strip()
        if key not in cache:
            cache[key] = _retrieve_for_query(key, filters)
        context, sources = cache[key]
        sub.result = context or "（无检索结果）"
        sub.sources = sources
    elif sub.intent.startswith("tool_"):
        sub.result = _run_tool_for_subtask(sub, prior_messages)
        sub.sources = []
    else:
        sub.result = ""
        sub.sources = []
    return sub


def execute_subtasks_parallel(
    sub_queries: list[SubQueryIntent],
    *,
    filters: dict,
    prior_messages: list[BaseMessage],
) -> list[SubQueryIntent]:
    start = time.perf_counter()
    rag_cache: dict[str, tuple[str, list[dict]]] = {}

    if len(sub_queries) <= 1:
        if not sub_queries:
            return []
        return [
            execute_subtask(
                sub_queries[0],
                filters=filters,
                prior_messages=prior_messages,
                rag_cache=rag_cache,
            )
        ]

    with ThreadPoolExecutor(max_workers=min(len(sub_queries), 4)) as pool:
        futures = [
            pool.submit(
                execute_subtask,
                sub,
                filters=filters,
                prior_messages=prior_messages,
                rag_cache=rag_cache,
            )
            for sub in sub_queries
        ]
        results = [f.result() for f in futures]

    parallel_exec_ms = round((time.perf_counter() - start) * 1000, 2)
    update_run_metadata(
        parallel_exec_ms=parallel_exec_ms,
        sub_intents=[{"id": s.id, "intent": s.intent, "text": s.text[:80]} for s in results],
    )
    return results


async def execute_subtasks_async(
    sub_queries: list[SubQueryIntent],
    *,
    filters: dict,
    prior_messages: list[BaseMessage],
) -> list[SubQueryIntent]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: execute_subtasks_parallel(
            sub_queries, filters=filters, prior_messages=prior_messages
        ),
    )


def _primary_intent(sub_queries: list[SubQueryIntent]) -> str:
    if not sub_queries:
        return "chat"
    if len(sub_queries) == 1:
        return sub_queries[0].intent
    intents = [s.intent for s in sub_queries if s.intent != "chat"]
    return intents[0] if intents else sub_queries[0].intent


def build_compound_stream_messages(
    original_query: str,
    sub_queries: list[SubQueryIntent],
) -> list[BaseMessage]:
    blocks = []
    for sub in sub_queries:
        blocks.append(
            f"### 子问题（{sub.id}）\n"
            f"问题：{sub.text}\n"
            f"意图：{sub.intent}\n"
            f"结果：\n{sub.result or '（无工具/RAG 结果，请基于常识简要回答）'}"
        )
    has_writing = any(s.intent == "tool_writing" for s in sub_queries)
    hint_intent = "tool_writing" if has_writing else "rag"
    prompt = COMPOUND_SYNTHESIS_PROMPT.format(
        original_query=strip_user_input(original_query),
        subtask_blocks="\n\n".join(blocks),
        structured_hint=structured_output_hint(hint_intent),
    )
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]


def merge_subtask_state(
    sub_queries: list[SubQueryIntent],
    *,
    original_query: str,
    filters: dict,
    prior_messages: list[BaseMessage],
) -> AgentState:
    rag_parts = []
    tool_parts = []
    all_sources: list[dict] = []
    seen_source_keys: set[str] = set()

    for sub in sub_queries:
        if sub.intent == "rag" and sub.result:
            rag_parts.append(f"[{sub.id}] {sub.text}\n{sub.result}")
        elif sub.intent.startswith("tool_") and sub.result:
            tool_parts.append(f"[{sub.id}] {sub.text}\n{sub.result}")
        for src in sub.sources:
            key = f"{src.get('title')}|{src.get('author')}|{src.get('source_file')}"
            if key not in seen_source_keys:
                seen_source_keys.add(key)
                all_sources.append(src)

    primary = _primary_intent(sub_queries)
    return {
        "messages": list(prior_messages) + [HumanMessage(content=original_query)],
        "intent": primary,
        "rag_context": "\n\n".join(rag_parts),
        "tool_result": "\n\n".join(tool_parts),
        "filters": filters,
        "source_refs": all_sources,
        "sub_queries": [s.model_dump() for s in sub_queries],
        "is_compound": len(sub_queries) > 1,
        "primary_intent": primary,
        "original_query": original_query,
    }


def build_compound_prepared(
    original_query: str,
    sub_queries: list[SubQueryIntent],
    state: AgentState,
) -> PreparedAgent:
    return {
        "state": state,
        "intent": state["primary_intent"],
        "mode": "compound_synthesis",
        "sub_intents": unique_sub_intents_for_display(sub_queries),
        "is_compound": should_use_compound_pipeline(sub_queries),
    }

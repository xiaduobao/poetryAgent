"""FastAPI 路由。"""
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.graph import (
    commit_agent_state,
    prepare_agent,
    run_agent,
    stream_final_answer,
)
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    RAGRequest,
    RAGResponse,
    ToolAllusionRequest,
    ToolAuthorRequest,
    ToolCompareRequest,
    ToolMeterRequest,
    ToolPoemRequest,
    ToolThemeRequest,
    ToolWritingRequest,
)
from app.agent.sources import build_sources_from_prepared
from app.db import crud
from app.db.database import get_session_factory
from app.observability.langsmith import (
    trace_metadata,
    trace_session,
    traceable,
    truncate_input,
    update_run_metadata,
)
from app.rag.retriever import get_hybrid_retriever
from app.security.filter import sanitize_input
from app.tools.author import query_author
from app.tools.allusion import explain_allusion
from app.tools.compare import compare_styles
from app.tools.meter import analyze_meter
from app.tools.poem_lookup import lookup_poem
from app.tools.theme import recommend_by_theme
from app.tools.writing import writing_guide

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_thread_id(req: ChatRequest) -> str:
    return req.session_id or req.thread_id


def _build_filters(req: ChatRequest | RAGRequest) -> dict:
    return {
        k: v
        for k, v in {
            "author": req.author,
            "dynasty": req.dynasty,
            "genre": req.genre,
        }.items()
        if v
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _status_phase(prepared_mode: str, intent: str) -> str:
    if prepared_mode == "rag":
        return "retrieving"
    if prepared_mode == "tool_summary":
        return "tooling"
    if intent != "chat":
        return "classifying"
    return "generating"


@traceable(run_type="chain", name="chat_request")
def _traced_run_agent(
    message: str,
    thread_id: str,
    filters: dict,
) -> dict:
    update_run_metadata(
        **trace_metadata(
            session_id=thread_id,
            stream=False,
            endpoint="/api/v1/chat",
            filters=filters or None,
            message_preview=truncate_input(message),
        )
    )
    with trace_session(thread_id):
        return run_agent(message, thread_id=thread_id, filters=filters)


@traceable(run_type="chain", name="chat_request")
async def _traced_stream_chat(
    message: str,
    thread_id: str,
    filters: dict,
) -> AsyncIterator[tuple[str, object]]:
    """在单个根 Run 内完成 prepare + stream，通过事件元组向外传递。"""
    update_run_metadata(
        **trace_metadata(
            session_id=thread_id,
            stream=True,
            endpoint="/api/v1/chat/stream",
            filters=filters or None,
            message_preview=truncate_input(message),
        )
    )
    with trace_session(thread_id):
        prepared = prepare_agent(message, thread_id=thread_id, filters=filters)
        yield ("prepared", prepared)
        async for token in stream_final_answer(prepared):
            yield ("token", token)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """多轮对话 Agent 入口（非流式）。"""
    text, err = sanitize_input(req.message)
    if err:
        raise HTTPException(status_code=400, detail=err)

    thread_id = _resolve_thread_id(req)
    filters = _build_filters(req)

    factory = get_session_factory()
    async with factory() as db:
        session = await crud.get_session(db, thread_id)
        if not session:
            session = await crud.create_session(db, title="新对话")
            thread_id = session.id
        await crud.add_message(db, thread_id, "user", text)
        await crud.auto_title_from_message(db, thread_id, text)
        await db.commit()

    try:
        result = _traced_run_agent(text, thread_id, filters)
    except Exception as e:
        logger.exception("agent error")
        raise HTTPException(status_code=500, detail=str(e)) from e

    async with factory() as db:
        await crud.add_message(
            db, thread_id, "assistant", result["answer"],
            intent=result.get("intent"),
            sources=result.get("sources"),
        )
        await db.commit()

    preview = (result.get("rag_context") or "")[:500] or None
    return ChatResponse(
        answer=result["answer"],
        intent=result.get("intent", ""),
        thread_id=thread_id,
        session_id=thread_id,
        rag_context_preview=preview,
    )


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """SSE 流式对话。"""
    text, err = sanitize_input(req.message)
    if err:
        raise HTTPException(status_code=400, detail=err)

    thread_id = _resolve_thread_id(req)
    filters = _build_filters(req)

    factory = get_session_factory()
    async with factory() as db:
        session = await crud.get_session(db, thread_id)
        if not session:
            session = await crud.create_session(db, title="新对话")
            thread_id = session.id
        user_msg = await crud.add_message(db, thread_id, "user", text)
        await crud.auto_title_from_message(db, thread_id, text)
        await db.commit()
        user_msg_id = user_msg.id if user_msg else ""

    async def event_generator() -> AsyncIterator[str]:
        full_answer = ""
        intent = ""
        sources: list = []
        assistant_msg_id = ""
        prepared = None
        try:
            yield _sse("status", {"phase": "classifying"})
            async for kind, value in _traced_stream_chat(text, thread_id, filters):
                if kind == "prepared":
                    prepared = value
                    intent = prepared["intent"]
                    sources = build_sources_from_prepared(prepared)
                    yield _sse(
                        "status",
                        {"phase": _status_phase(prepared["mode"], intent)},
                    )
                    if sources:
                        yield _sse("sources", {"sources": sources})
                    yield _sse("status", {"phase": "generating"})
                elif kind == "token":
                    token = str(value)
                    full_answer += token
                    yield _sse("token", {"content": token})

            if prepared is None:
                raise RuntimeError("agent prepare stage did not complete")

            commit_agent_state(thread_id, text, full_answer, prepared)

            async with factory() as db:
                msg = await crud.add_message(
                    db,
                    thread_id,
                    "assistant",
                    full_answer,
                    intent=intent,
                    sources=sources or None,
                )
                await db.commit()
                assistant_msg_id = msg.id if msg else ""

            yield _sse(
                "done",
                {
                    "session_id": thread_id,
                    "intent": intent,
                    "message_id": assistant_msg_id,
                    "user_message_id": user_msg_id,
                    "sources": sources,
                },
            )
        except Exception as e:
            logger.exception("stream agent error")
            yield _sse("error", {"detail": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@traceable(run_type="retriever", name="rag_search")
def _traced_rag_search(
    query: str,
    *,
    author: str | None = None,
    dynasty: str | None = None,
    genre: str | None = None,
    top_k: int = 4,
) -> list:
    filters = {
        k: v
        for k, v in {
            "author": author,
            "dynasty": dynasty,
            "genre": genre,
        }.items()
        if v
    }
    update_run_metadata(
        **trace_metadata(
            endpoint="/api/v1/rag",
            filters=filters or None,
            query_preview=truncate_input(query),
        )
    )
    retriever = get_hybrid_retriever()
    return retriever.retrieve(
        query,
        author=author,
        dynasty=dynasty,
        genre=genre,
    )[:top_k]


@router.post("/rag", response_model=RAGResponse)
async def rag_search(req: RAGRequest) -> RAGResponse:
    """纯 RAG 检索接口。"""
    text, err = sanitize_input(req.query)
    if err:
        raise HTTPException(status_code=400, detail=err)

    docs = _traced_rag_search(
        text,
        author=req.author,
        dynasty=req.dynasty,
        genre=req.genre,
        top_k=req.top_k,
    )

    return RAGResponse(
        query=text,
        documents=[
            {
                "content": d.page_content[:1500],
                "metadata": d.metadata,
            }
            for d in docs
        ],
    )


@traceable(run_type="tool", name="tool_author")
def _traced_tool_author(name: str) -> dict:
    update_run_metadata(**trace_metadata(endpoint="/api/v1/tools/author"))
    return query_author(name)


@traceable(run_type="tool", name="tool_meter")
def _traced_tool_meter(title: str, content: str) -> dict:
    update_run_metadata(**trace_metadata(endpoint="/api/v1/tools/meter"))
    return analyze_meter(title, content)


@traceable(run_type="tool", name="tool_compare")
def _traced_tool_compare(author_a: str, author_b: str) -> dict:
    update_run_metadata(**trace_metadata(endpoint="/api/v1/tools/compare"))
    return compare_styles(author_a, author_b)


@router.post("/tools/author")
async def tool_author(req: ToolAuthorRequest):
    return _traced_tool_author(req.name)


@router.post("/tools/meter")
async def tool_meter(req: ToolMeterRequest):
    return _traced_tool_meter(req.title, req.content)


@router.post("/tools/compare")
async def tool_compare(req: ToolCompareRequest):
    return _traced_tool_compare(req.author_a, req.author_b)


@traceable(run_type="tool", name="tool_poem")
def _traced_tool_poem(title: str, author: str) -> dict:
    update_run_metadata(**trace_metadata(endpoint="/api/v1/tools/poem"))
    return lookup_poem(title, author)


@traceable(run_type="tool", name="tool_theme")
def _traced_tool_theme(theme: str, limit: int) -> dict:
    update_run_metadata(**trace_metadata(endpoint="/api/v1/tools/theme"))
    return recommend_by_theme(theme, limit=limit)


@traceable(run_type="tool", name="tool_allusion")
def _traced_tool_allusion(query: str) -> dict:
    update_run_metadata(**trace_metadata(endpoint="/api/v1/tools/allusion"))
    return explain_allusion(query)


@traceable(run_type="tool", name="tool_writing")
def _traced_tool_writing(writing_type: str, theme: str, constraints: str) -> dict:
    update_run_metadata(**trace_metadata(endpoint="/api/v1/tools/writing"))
    return writing_guide(writing_type, theme, constraints)


@router.post("/tools/poem")
async def tool_poem(req: ToolPoemRequest):
    return _traced_tool_poem(req.title, req.author)


@router.post("/tools/theme")
async def tool_theme(req: ToolThemeRequest):
    return _traced_tool_theme(req.theme, req.limit)


@router.post("/tools/allusion")
async def tool_allusion(req: ToolAllusionRequest):
    return _traced_tool_allusion(req.query)


@router.post("/tools/writing")
async def tool_writing(req: ToolWritingRequest):
    return _traced_tool_writing(req.writing_type, req.theme, req.constraints)


@router.get("/health")
async def health():
    return {"status": "ok", "service": "poetry-agent"}

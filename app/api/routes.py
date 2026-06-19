"""FastAPI 路由。"""
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import (
    commit_agent_state,
    prepare_agent,
    run_agent,
    stream_final_answer,
)
from app.agent.sources import build_sources_from_prepared
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
from app.auth.dependencies import get_current_user
from app.auth.quota import require_chat_quota, require_rag_quota
from app.config import get_settings
from app.db import crud
from app.db.database import get_db, get_session_factory
from app.db.models import User
from app.observability.health import readiness_report
from app.observability.langsmith import (
    trace_metadata,
    trace_session,
    traceable,
    truncate_input,
    update_run_metadata,
)
from app.observability.metrics import RAG_EMPTY
from app.observability.tokens import record_llm_tokens
from app.rag.retriever import get_hybrid_retriever
from app.security.filter import sanitize_input_async, wrap_user_input
from app.security.rate_limit import limiter
from app.tools.allusion import explain_allusion
from app.tools.author import query_author
from app.tools.compare import compare_styles
from app.tools.meter import analyze_meter
from app.tools.poem_lookup import lookup_poem
from app.tools.theme import recommend_by_theme
from app.tools.writing import writing_guide
from app.vision.describe import (
    build_image_writing_message,
    describe_image_for_poetry,
    validate_image_base64,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _trace_ctx(request: Request, user: User) -> dict:
    return trace_metadata(
        user_id=user.id,
        tenant_id=user.tenant_id,
        request_id=getattr(request.state, "request_id", None),
    )


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


def _status_phase(prepared_mode: str, intent: str, is_compound: bool = False) -> str:
    if is_compound and prepared_mode == "compound_synthesis":
        return "executing"
    if prepared_mode == "compound_synthesis":
        return "generating"
    if prepared_mode == "rag":
        return "retrieving"
    if prepared_mode == "tool_summary":
        return "tooling"
    if intent != "chat":
        return "classifying"
    return "generating"


def _has_image(req: ChatRequest) -> bool:
    return bool(req.image_base64 and req.image_base64.strip())


async def _sanitize_user_text(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return ""
    cleaned, err = await sanitize_input_async(text)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return cleaned


async def _resolve_agent_message(req: ChatRequest) -> tuple[str, bool]:
    """解析聊天输入：有图时先做视觉描述并合成增强消息。返回 (agent_message, has_image)。"""
    has_image = _has_image(req)
    user_text = await _sanitize_user_text(req.message)

    if not has_image:
        return user_text, False

    try:
        image_bytes, mime = validate_image_base64(req.image_base64 or "")
        vision_output = describe_image_for_poetry(image_bytes, mime)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("vision describe error")
        raise HTTPException(status_code=500, detail=f"画面理解失败: {e}") from e

    return build_image_writing_message(vision_output, user_text), True


@traceable(run_type="chain", name="chat_request")
def _traced_run_agent(
    message: str,
    thread_id: str,
    filters: dict,
    meta: dict,
) -> dict:
    update_run_metadata(
        **meta,
        session_id=thread_id,
        stream=False,
        endpoint="/api/v1/chat",
        filters=filters or None,
        message_preview=truncate_input(message),
    )
    with trace_session(thread_id):
        return run_agent(wrap_user_input(message), thread_id=thread_id, filters=filters)


@traceable(run_type="chain", name="chat_request")
async def _traced_stream_chat(
    message: str,
    thread_id: str,
    filters: dict,
    meta: dict,
) -> AsyncIterator[tuple[str, object]]:
    update_run_metadata(
        **meta,
        session_id=thread_id,
        stream=True,
        endpoint="/api/v1/chat/stream",
        filters=filters or None,
        message_preview=truncate_input(message),
    )
    settings = get_settings()
    with trace_session(thread_id):
        if settings.compound_intent_enabled:
            yield ("status", {"phase": "decomposing"})
        else:
            yield ("status", {"phase": "classifying"})
        prepared = prepare_agent(wrap_user_input(message), thread_id=thread_id, filters=filters)
        yield ("prepared", prepared)
        sub_intents = prepared.get("sub_intents") or []
        if len(sub_intents) > 1 and prepared.get("is_compound"):
            yield (
                "subtasks",
                {
                    "sub_total": len(sub_intents),
                    "sub_intents": sub_intents,
                    "is_compound": True,
                },
            )
        async for token in stream_final_answer(prepared):
            yield ("token", token)


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(lambda: get_settings().rate_limit_chat)
async def chat(
    request: Request,
    req: ChatRequest,
    user: User = Depends(require_chat_quota),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    text, has_image = await _resolve_agent_message(req)

    thread_id = _resolve_thread_id(req)
    filters = _build_filters(req)
    meta = {**_trace_ctx(request, user), "has_image": has_image}

    session = await crud.get_session(db, thread_id, user_id=user.id)
    if not session:
        if thread_id not in ("default", ""):
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        session = await crud.create_session(db, user.id, title="新对话")
        thread_id = session.id

    await crud.add_message(db, thread_id, user.id, "user", text)
    await crud.auto_title_from_message(db, thread_id, user.id, text)
    await db.commit()

    try:
        result = _traced_run_agent(text, thread_id, filters, meta)
    except Exception as e:
        logger.exception("agent error")
        raise HTTPException(status_code=500, detail=str(e)) from e

    tokens_used = int(result.get("tokens_used") or 0)
    factory = get_session_factory()
    async with factory() as db2:
        await crud.add_message(
            db2, thread_id, user.id, "assistant", result["answer"],
            intent=result.get("intent"),
            sources=result.get("sources"),
        )
        await crud.record_usage(
            db2,
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="chat",
            tokens=tokens_used,
        )
        record_llm_tokens("chat", tokens_used)
        await db2.commit()

    preview = (result.get("rag_context") or "")[:500] or None
    return ChatResponse(
        answer=result["answer"],
        intent=result.get("intent", ""),
        thread_id=thread_id,
        session_id=thread_id,
        rag_context_preview=preview,
    )


@router.post("/chat/stream")
@limiter.limit(lambda: get_settings().rate_limit_chat)
async def chat_stream(
    request: Request,
    req: ChatRequest,
    user: User = Depends(require_chat_quota),
) -> StreamingResponse:
    has_image = _has_image(req)
    user_text = await _sanitize_user_text(req.message)

    if has_image:
        try:
            validate_image_base64(req.image_base64 or "")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    thread_id = _resolve_thread_id(req)
    filters = _build_filters(req)
    meta = {**_trace_ctx(request, user), "has_image": has_image}

    factory = get_session_factory()
    async with factory() as db_init:
        session = await crud.get_session(db_init, thread_id, user_id=user.id)
        if not session:
            if thread_id not in ("default", ""):
                raise HTTPException(status_code=404, detail="会话不存在或无权访问")
            session = await crud.create_session(db_init, user.id, title="新对话")
            thread_id = session.id
        await db_init.commit()

    async def event_generator() -> AsyncIterator[str]:
        full_answer = ""
        intent = ""
        sources: list = []
        assistant_msg_id = ""
        user_msg_id = ""
        prepared = None
        text = user_text
        try:
            if has_image:
                yield _sse("status", {"phase": "describing"})
                image_bytes, mime = validate_image_base64(req.image_base64 or "")
                vision_output = describe_image_for_poetry(image_bytes, mime)
                text = build_image_writing_message(vision_output, user_text)

            factory = get_session_factory()
            async with factory() as db_user:
                user_msg = await crud.add_message(db_user, thread_id, user.id, "user", text)
                await crud.auto_title_from_message(db_user, thread_id, user.id, text)
                await db_user.commit()
                user_msg_id = user_msg.id if user_msg else ""

            async for kind, value in _traced_stream_chat(text, thread_id, filters, meta):
                if kind == "status":
                    yield _sse("status", value)
                elif kind == "subtasks":
                    yield _sse("subtasks", value)
                elif kind == "prepared":
                    prepared = value
                    intent = prepared["intent"]
                    sources = build_sources_from_prepared(prepared)
                    yield _sse(
                        "status",
                        {
                            "phase": _status_phase(
                                prepared["mode"],
                                intent,
                                is_compound=bool(prepared.get("is_compound")),
                            )
                        },
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

            factory = get_session_factory()
            async with factory() as db2:
                msg = await crud.add_message(
                    db2, thread_id, user.id, "assistant", full_answer,
                    intent=intent, sources=sources or None,
                )
                tokens_used = int((prepared or {}).get("token_usage") or 0)
                await crud.record_usage(
                    db2,
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    action="chat",
                    tokens=tokens_used,
                )
                record_llm_tokens("chat", tokens_used)
                await db2.commit()
                assistant_msg_id = msg.id if msg else ""

            yield _sse("done", {
                "session_id": thread_id,
                "intent": intent,
                "message_id": assistant_msg_id,
                "user_message_id": user_msg_id,
                "sources": sources,
                "sub_intents": (prepared or {}).get("sub_intents"),
                "is_compound": bool((prepared or {}).get("is_compound")),
            })
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
    meta: dict | None = None,
) -> list:
    filters = {k: v for k, v in {"author": author, "dynasty": dynasty, "genre": genre}.items() if v}
    update_run_metadata(**(meta or {}), endpoint="/api/v1/rag", filters=filters or None, query_preview=truncate_input(query))
    retriever = get_hybrid_retriever()
    docs = retriever.retrieve(query, author=author, dynasty=dynasty, genre=genre)[:top_k]
    if not docs:
        RAG_EMPTY.inc()
    return docs


@router.post("/rag", response_model=RAGResponse)
@limiter.limit(lambda: get_settings().rate_limit_rag)
async def rag_search(
    request: Request,
    req: RAGRequest,
    user: User = Depends(require_rag_quota),
    db: AsyncSession = Depends(get_db),
) -> RAGResponse:
    text, err = await sanitize_input_async(req.query)
    if err:
        raise HTTPException(status_code=400, detail=err)

    sub = await crud.get_subscription(db, user.tenant_id)
    top_k = min(req.top_k, sub.rag_top_k if sub else req.top_k)

    docs = _traced_rag_search(
        text,
        author=req.author,
        dynasty=req.dynasty,
        genre=req.genre,
        top_k=top_k,
        meta=_trace_ctx(request, user),
    )
    await crud.record_usage(db, tenant_id=user.tenant_id, user_id=user.id, action="rag")

    return RAGResponse(
        query=text,
        documents=[{"content": d.page_content[:1500], "metadata": d.metadata} for d in docs],
    )


@router.post("/tools/author")
@limiter.limit(lambda: get_settings().rate_limit_default)
async def tool_author(request: Request, req: ToolAuthorRequest, user: User = Depends(get_current_user)):
    return query_author(req.name)


@router.post("/tools/meter")
@limiter.limit(lambda: get_settings().rate_limit_default)
async def tool_meter(request: Request, req: ToolMeterRequest, user: User = Depends(get_current_user)):
    return analyze_meter(req.title, req.content)


@router.post("/tools/compare")
@limiter.limit(lambda: get_settings().rate_limit_default)
async def tool_compare(request: Request, req: ToolCompareRequest, user: User = Depends(get_current_user)):
    return compare_styles(req.author_a, req.author_b)


@router.post("/tools/poem")
@limiter.limit(lambda: get_settings().rate_limit_default)
async def tool_poem(request: Request, req: ToolPoemRequest, user: User = Depends(get_current_user)):
    return lookup_poem(req.title, req.author)


@router.post("/tools/theme")
@limiter.limit(lambda: get_settings().rate_limit_default)
async def tool_theme(request: Request, req: ToolThemeRequest, user: User = Depends(get_current_user)):
    return recommend_by_theme(req.theme, limit=req.limit)


@router.post("/tools/allusion")
@limiter.limit(lambda: get_settings().rate_limit_default)
async def tool_allusion(request: Request, req: ToolAllusionRequest, user: User = Depends(get_current_user)):
    return explain_allusion(req.query)


@router.post("/tools/writing")
@limiter.limit(lambda: get_settings().rate_limit_default)
async def tool_writing(request: Request, req: ToolWritingRequest, user: User = Depends(get_current_user)):
    return writing_guide(req.writing_type, req.theme, req.constraints)


@router.get("/health")
async def health():
    return {"status": "ok", "service": "poetry-agent"}


@router.get("/health/ready")
async def health_ready():
    report = await readiness_report()
    if report["status"] != "ready":
        raise HTTPException(status_code=503, detail=report)
    return report

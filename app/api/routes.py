"""FastAPI 路由。"""
import logging

from fastapi import APIRouter, HTTPException

from app.agent.graph import run_agent
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    RAGRequest,
    RAGResponse,
    ToolAuthorRequest,
    ToolCompareRequest,
    ToolMeterRequest,
)
from app.rag.retriever import format_context, get_hybrid_retriever
from app.security.filter import sanitize_input
from app.tools.author import query_author
from app.tools.compare import compare_styles
from app.tools.meter import analyze_meter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """多轮对话 Agent 入口。"""
    text, err = sanitize_input(req.message)
    if err:
        raise HTTPException(status_code=400, detail=err)

    filters = {
        k: v
        for k, v in {
            "author": req.author,
            "dynasty": req.dynasty,
            "genre": req.genre,
        }.items()
        if v
    }

    try:
        result = run_agent(text, thread_id=req.thread_id, filters=filters)
    except Exception as e:
        logger.exception("agent error")
        raise HTTPException(status_code=500, detail=str(e)) from e

    preview = (result.get("rag_context") or "")[:500] or None
    return ChatResponse(
        answer=result["answer"],
        intent=result.get("intent", ""),
        thread_id=req.thread_id,
        rag_context_preview=preview,
    )


@router.post("/rag", response_model=RAGResponse)
async def rag_search(req: RAGRequest) -> RAGResponse:
    """纯 RAG 检索接口。"""
    text, err = sanitize_input(req.query)
    if err:
        raise HTTPException(status_code=400, detail=err)

    retriever = get_hybrid_retriever()
    docs = retriever.retrieve(
        text,
        author=req.author,
        dynasty=req.dynasty,
        genre=req.genre,
    )[: req.top_k]

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


@router.post("/tools/author")
async def tool_author(req: ToolAuthorRequest):
    return query_author(req.name)


@router.post("/tools/meter")
async def tool_meter(req: ToolMeterRequest):
    return analyze_meter(req.title, req.content)


@router.post("/tools/compare")
async def tool_compare(req: ToolCompareRequest):
    return compare_styles(req.author_a, req.author_b)


@router.get("/health")
async def health():
    return {"status": "ok", "service": "poetry-agent"}

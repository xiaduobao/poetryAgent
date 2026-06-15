"""FastAPI 应用入口。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.rag.indexer import build_vector_store

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时确保向量库已构建。"""
    logger.info("Building / loading vector store...")
    try:
        build_vector_store()
        logger.info("Vector store ready.")
    except Exception as e:
        logger.warning("Vector store init skipped or failed: %s", e)
    yield


app = FastAPI(
    title="古典诗词鉴赏智能助手",
    description="诗词知识库 RAG + LangGraph Agent + 工具链",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": "古典诗词鉴赏智能助手",
        "docs": "/docs",
        "endpoints": {
            "chat": "POST /api/v1/chat",
            "rag": "POST /api/v1/rag",
            "tools": "POST /api/v1/tools/{author|meter|compare}",
        },
    }

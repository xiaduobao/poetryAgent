"""FastAPI 应用入口。"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.session_routes import router as session_router
from app.config import ROOT_DIR, get_settings
from app.db.database import init_db
from app.observability.langsmith import init_langsmith
from app.rag.indexer import build_vector_store

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库与向量库。"""
    settings = get_settings()
    init_langsmith(settings)
    if settings.langsmith_tracing and settings.langsmith_api_key:
        logger.info("LangSmith tracing enabled (project=%s).", settings.langsmith_project)
    await init_db()
    logger.info("Session database ready.")
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
app.include_router(session_router, prefix="/api/v1")


@app.get("/api")
async def api_info():
    return {
        "name": "古典诗词鉴赏智能助手",
        "docs": "/docs",
        "endpoints": {
            "chat": "POST /api/v1/chat",
            "chat_stream": "POST /api/v1/chat/stream",
            "sessions": "GET/POST /api/v1/sessions",
            "rag": "POST /api/v1/rag",
            "tools": "POST /api/v1/tools/{author|meter|compare}",
        },
    }


if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    async def spa_index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api") or full_path == "docs" or full_path.startswith("openapi"):
            raise HTTPException(status_code=404)
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    async def root():
        return {
            "name": "古典诗词鉴赏智能助手",
            "docs": "/docs",
            "hint": "前端未构建，请运行 cd frontend && npm run build",
            "endpoints": {
                "chat": "POST /api/v1/chat",
                "chat_stream": "POST /api/v1/chat/stream",
                "sessions": "GET/POST /api/v1/sessions",
            },
        }

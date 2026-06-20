"""FastAPI 应用入口。"""
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    _PROMETHEUS = True
except ImportError:
    _PROMETHEUS = False

from app.agent.checkpoint import setup_checkpointer, shutdown_checkpointer
from app.api.admin_routes import router as admin_router
from app.api.corpus_routes import router as corpus_router
from app.api.routes import router
from app.api.session_routes import router as session_router
from app.auth.routes import router as auth_router
from app.config import ROOT_DIR, get_settings
from app.db.database import init_db
from app.middleware.metrics import MetricsMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.observability.langsmith import init_langsmith
from app.observability.logging_setup import setup_logging
from app.observability.sentry import init_sentry
from app.rag.indexer import build_vector_store
from app.security.rate_limit import limiter

logger = logging.getLogger(__name__)

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
_metrics_basic = HTTPBasic(auto_error=False)


def _verify_metrics_auth(credentials: HTTPBasicCredentials | None = Depends(_metrics_basic)) -> None:
    settings = get_settings()
    if not settings.metrics_basic_auth_user:
        return
    if credentials is None:
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})
    user_ok = secrets.compare_digest(credentials.username, settings.metrics_basic_auth_user)
    pass_ok = secrets.compare_digest(credentials.password, settings.metrics_basic_auth_password)
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings)
    init_sentry(settings)
    init_langsmith(settings)
    if settings.langsmith_tracing and settings.langsmith_api_key:
        logger.info("LangSmith tracing enabled (project=%s).", settings.langsmith_project)
    await init_db()
    await setup_checkpointer()
    logger.info("Database ready.")
    logger.info("Loading RAG models (local only)...")
    from app.rag.embedder import warmup_rag_models

    warmup_rag_models(settings)
    logger.info("Building / loading vector store...")
    build_vector_store()
    logger.info("Vector store ready.")
    logger.info("Warming up hybrid retriever...")
    from app.rag.retriever import get_hybrid_retriever

    get_hybrid_retriever()
    logger.info("Hybrid retriever ready.")
    yield
    await shutdown_checkpointer()


def create_app() -> FastAPI:
    settings = get_settings()
    docs_url = None if settings.is_production else "/docs"
    redoc_url = None if settings.is_production else "/redoc"
    openapi_url = None if settings.is_production else "/openapi.json"

    app = FastAPI(
        title="古典诗词鉴赏智能助手",
        description="诗词知识库 RAG + LangGraph Agent + 工具链",
        version="2.0.0",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    origins = settings.cors_origin_list or ["http://localhost:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(router, prefix="/api/v1")
    app.include_router(session_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(corpus_router, prefix="/api/v1")

    @app.get("/api")
    async def api_info():
        return {
            "name": "古典诗词鉴赏智能助手",
            "version": "2.0.0",
            "docs": docs_url,
            "auth": "POST /api/v1/auth/login",
        }

    @app.get("/metrics")
    async def metrics(_: None = Depends(_verify_metrics_auth)):
        if not _PROMETHEUS:
            raise HTTPException(status_code=503, detail="prometheus_client 未安装")
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

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
            return {"name": "古典诗词鉴赏智能助手", "hint": "前端未构建"}

    return app


app = create_app()

"""应用配置。"""
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


def _resolve_env_file() -> Path:
    """本地 dev 用 .env，生产用 .env.prod（可通过 ENV_FILE 覆盖）。"""
    override = os.getenv("ENV_FILE", "").strip()
    if override:
        return ROOT_DIR / override
    if os.getenv("APP_ENV", "").lower() in ("production", "prod"):
        prod = ROOT_DIR / ".env.prod"
        if prod.exists():
            return prod
    return ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 环境
    app_env: str = "development"
    debug: bool = False

    openai_api_key: str = ""
    openai_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-plus"
    vision_model: str = "qwen-vl-max"
    # ReAct 工具多轮 / 低置信兜底专用；留空则与 LLM_MODEL 相同
    react_llm_model: str = "qwen-turbo"
    # qwen3.7-plus 等混合思考模型默认开启思考，Agent 多轮调用会显著变慢；一般对话建议 false
    llm_enable_thinking: bool = False

    embedding_model: str = "./data/models/bge-small-zh-v1.5"
    rerank_model: str = "./data/models/BAAI--bge-reranker-base"
    hf_endpoint: str = ""

    chroma_persist_dir: str = str(ROOT_DIR / "data" / "chroma_db")
    corpus_dir: str = str(ROOT_DIR / "data" / "corpus")
    authors_db: str = str(ROOT_DIR / "data" / "authors.json")
    sessions_db: str = str(ROOT_DIR / "data" / "sessions.db")
    database_url: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    log_json: bool = False

    chunk_overlap_tokens: int = 100
    retrieval_top_k: int = 8
    rerank_top_n: int = 4
    rerank_enabled: bool = True
    rerank_max_candidates: int = 6
    rerank_max_length: int = 512
    rerank_batch_size: int = 16

    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "poetry-agent"

    # JWT 认证
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    # 游客访问
    guest_enabled: bool = True
    guest_daily_chat_limit: int = 20
    guest_daily_rag_limit: int = 20
    guest_access_expire_hours: int = 24

    # CORS（逗号分隔）
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    # 限流
    rate_limit_enabled: bool = True
    rate_limit_default: str = "120/hour"
    rate_limit_chat: str = "15/minute"
    rate_limit_rag: str = "30/minute"
    rate_limit_storage_uri: str = ""

    # 内容安全（阿里云，可选）
    content_moderation_enabled: bool = False
    aliyun_access_key_id: str = ""
    aliyun_access_key_secret: str = ""
    aliyun_region: str = "cn-shanghai"

    # Redis（Checkpoint / 限流）
    redis_url: str = ""

    # Sentry
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1

    # Prometheus metrics 保护
    metrics_basic_auth_user: str = ""
    metrics_basic_auth_password: str = ""

    # 告警 Webhook（钉钉/飞书）
    alert_webhook_url: str = ""

    # 复合意图：单条消息多问题拆解与并行执行
    compound_intent_enabled: bool = False

    # 有限 ReAct：工具多轮 / 低置信度兜底 / RAG-as-tool
    react_enabled: bool = True
    react_max_steps: int = 3
    react_low_confidence_threshold: float = 0.65
    react_low_confidence_fallback: bool = True
    react_tool_loop_enabled: bool = True  # 低置信度/指代性 tool 才走 ReAct，高置信度走 legacy 单轮
    react_rag_as_tool_enabled: bool = True
    react_rag_max_searches: int = 2

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def apply_hf_hub_env(settings: Settings | None = None) -> None:
    """将 HF 镜像写入环境变量，供 huggingface_hub / sentence-transformers 使用。"""
    from app.hf_bootstrap import bootstrap_hf_hub_env

    bootstrap_hf_hub_env()
    s = settings or Settings()
    endpoint = (s.hf_endpoint or os.getenv("HF_ENDPOINT") or "").strip().rstrip("/")
    if not endpoint:
        return
    os.environ["HF_ENDPOINT"] = endpoint
    os.environ["HUGGINGFACE_HUB_ENDPOINT"] = endpoint


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    apply_hf_hub_env(s)
    return s

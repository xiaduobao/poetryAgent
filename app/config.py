"""应用配置。"""
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-plus"

    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rerank_model: str = "BAAI/bge-reranker-base"
    # 无法直连 huggingface.co 时设为镜像，如 https://hf-mirror.com
    hf_endpoint: str = ""

    chroma_persist_dir: str = str(ROOT_DIR / "data" / "chroma_db")
    corpus_dir: str = str(ROOT_DIR / "data" / "corpus")
    authors_db: str = str(ROOT_DIR / "data" / "authors.json")

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    chunk_overlap_tokens: int = 100
    retrieval_top_k: int = 8
    rerank_top_n: int = 4


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

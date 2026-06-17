"""BGE 中文 Embedding。"""
import logging
import os
from functools import lru_cache
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings

from app.config import ROOT_DIR, Settings, get_settings

logger = logging.getLogger(__name__)


def resolve_model_path(model: str, *, label: str = "model") -> str:
    """将 .env 中的相对路径解析为本地目录；不存在则报错，不回落到 HuggingFace 远端。"""
    raw = (model or "").strip()
    if not raw:
        raise ValueError(
            f"{label} 未配置，请在 .env 中设置本地相对路径，例如 ./data/models/BAAI--bge-small-zh-v1.5"
        )
    p = Path(raw)
    resolved = p.resolve() if p.is_absolute() else (ROOT_DIR / raw).resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(
            f"{label} 本地目录不存在: env={raw!r}, resolved={resolved}. "
            "请确认路径与 data/models/ 下实际目录名一致，或执行 python scripts/download_models.py"
        )
    return str(resolved)


def _enforce_offline_hub() -> None:
    """禁止 huggingface_hub / transformers 在运行时访问远端。"""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


@lru_cache
def get_embeddings() -> HuggingFaceEmbeddings:
    settings = get_settings()
    raw = settings.embedding_model.strip()
    path = resolve_model_path(raw, label="EMBEDDING_MODEL")
    logger.info("Loading embedding model: env=%r resolved=%s", raw, path)
    _enforce_offline_hub()
    return HuggingFaceEmbeddings(
        model_name=path,
        model_kwargs={"device": "cpu", "local_files_only": True},
        encode_kwargs={"normalize_embeddings": True},
    )


def warmup_rag_models(settings: Settings | None = None) -> None:
    """启动时预加载 embedding / rerank；任一步失败则抛错终止启动。"""
    s = settings or get_settings()
    _enforce_offline_hub()

    get_embeddings()
    logger.info("Embedding model ready.")

    if not s.rerank_enabled:
        logger.info("RERANK_ENABLED=false，跳过 rerank 模型加载。")
        return

    from app.rag.retriever import get_reranker

    get_reranker()
    logger.info("Rerank model ready.")

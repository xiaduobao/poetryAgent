"""BGE 中文 Embedding。"""
from functools import lru_cache
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings

from app.config import ROOT_DIR, get_settings


def resolve_model_path(model: str) -> str:
    """将项目内相对路径解析为绝对路径，便于加载本地模型目录。"""
    p = Path(model)
    if p.is_dir():
        return str(p.resolve())
    if not p.is_absolute():
        candidate = ROOT_DIR / model
        if candidate.is_dir():
            return str(candidate.resolve())
    return model


@lru_cache
def get_embeddings() -> HuggingFaceEmbeddings:
    settings = get_settings()
    model_name = resolve_model_path(settings.embedding_model)
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

"""文档入库：加载 → 分块 → 向量化 → Chroma。"""
from pathlib import Path

from langchain_chroma import Chroma

from app.config import get_settings
from app.rag.chunker import load_poetry_documents, split_with_overlap
from app.rag.embedder import get_embeddings


def build_vector_store(force: bool = False) -> Chroma:
    """构建或加载 Chroma 向量库。"""
    settings = get_settings()
    persist_dir = Path(settings.chroma_persist_dir)
    embeddings = get_embeddings()

    if persist_dir.exists() and not force and any(persist_dir.iterdir()):
        return Chroma(
            persist_directory=str(persist_dir),
            embedding_function=embeddings,
            collection_name="poetry_corpus",
        )

    persist_dir.mkdir(parents=True, exist_ok=True)
    raw = load_poetry_documents(settings.corpus_dir)
    chunks = split_with_overlap(raw)

    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(persist_dir),
        collection_name="poetry_corpus",
    )


def get_vector_store() -> Chroma:
    settings = get_settings()
    return Chroma(
        persist_directory=settings.chroma_persist_dir,
        embedding_function=get_embeddings(),
        collection_name="poetry_corpus",
    )

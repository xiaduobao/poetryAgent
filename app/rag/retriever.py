"""混合检索 + BGE Rerank。"""
import logging
import time
import warnings
from functools import lru_cache

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.observability.langsmith import traceable, update_run_metadata
from app.rag.chunker import load_poetry_documents, split_with_overlap
from app.rag.indexer import get_vector_store

logger = logging.getLogger(__name__)

_reranker = None


def _rerank_device_fp16() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except ImportError:
        return False


def _rerank_passage(doc: Document, max_chars: int) -> str:
    """Rerank 用短文本：标题/作者 + 正文前缀，避免对整篇鉴赏全文打分。"""
    title = str(doc.metadata.get("title", "")).strip()
    author = str(doc.metadata.get("author", "")).strip()
    header = f"{title} {author}".strip()
    body = doc.page_content.strip()
    if header and header not in body[:80]:
        text = f"{header}\n{body}"
    else:
        text = body
    return text[:max_chars]


@traceable(run_type="retriever", name="load_reranker")
def _load_reranker():
    """首次加载 BGE Rerank 权重（冷启动时单独可见）。"""
    settings = get_settings()
    raw = settings.rerank_model.strip()
    if not raw:
        raise ValueError("RERANK_MODEL 未配置，请在 .env / .env.prod 中设置 rerank 模型相对路径")

    from FlagEmbedding import FlagReranker

    from app.rag.embedder import _enforce_offline_hub, resolve_model_path

    path = resolve_model_path(raw, label="RERANK_MODEL")
    use_fp16 = _rerank_device_fp16()
    logger.info("Loading rerank model: env=%r resolved=%s (fp16=%s)", raw, path, use_fp16)
    _enforce_offline_hub()
    return FlagReranker(path, use_fp16=use_fp16)


def get_reranker():
    """返回已加载的 BGE Rerank 模型（必须配置 RERANK_MODEL）。"""
    global _reranker
    if _reranker is not None:
        return _reranker
    _reranker = _load_reranker()
    return _reranker


def _tokenize_zh(text: str) -> list[str]:
    """简易中文分词：按字+双字切分。"""
    chars = list(text)
    bigrams = [text[i : i + 2] for i in range(len(text) - 1)]
    return chars + bigrams


class HybridRetriever:
    """向量检索 + BM25 关键词检索，合并去重后 Rerank。"""

    def __init__(self):
        self.settings = get_settings()
        self.vector_store = get_vector_store()
        self.vector_retriever = self.vector_store.as_retriever(
            search_kwargs={"k": self.settings.retrieval_top_k}
        )
        chunks = split_with_overlap(
            load_poetry_documents(self.settings.corpus_dir)
        )
        self.corpus_docs = chunks
        tokenized = [_tokenize_zh(d.page_content) for d in chunks]
        self.bm25 = BM25Okapi(tokenized)

    @traceable(run_type="retriever", name="bm25_search")
    def _bm25_search(self, query: str, k: int) -> list[Document]:
        tokens = _tokenize_zh(query)
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:k]
        docs = [self.corpus_docs[i] for i in ranked if scores[i] > 0]
        update_run_metadata(bm25_hits=len(docs), corpus_size=len(self.corpus_docs))
        return docs

    def _merge_docs(
        self,
        vector_docs: list[Document],
        keyword_docs: list[Document],
    ) -> list[Document]:
        seen: set[str] = set()
        merged: list[Document] = []
        for doc in vector_docs + keyword_docs:
            key = doc.page_content[:200]
            if key not in seen:
                seen.add(key)
                merged.append(doc)
        return merged

    @traceable(run_type="retriever", name="hybrid_retrieve")
    def retrieve(
        self,
        query: str,
        *,
        author: str | None = None,
        dynasty: str | None = None,
        genre: str | None = None,
    ) -> list[Document]:
        k = self.settings.retrieval_top_k
        timings_ms: dict[str, float] = {}

        t0 = time.perf_counter()
        vector_docs = self.vector_retriever.invoke(query)
        timings_ms["vector"] = round((time.perf_counter() - t0) * 1000, 1)

        t0 = time.perf_counter()
        keyword_docs = self._bm25_search(query, k)
        timings_ms["bm25"] = round((time.perf_counter() - t0) * 1000, 1)

        t0 = time.perf_counter()
        merged = self._merge_docs(vector_docs, keyword_docs)
        timings_ms["merge"] = round((time.perf_counter() - t0) * 1000, 1)

        if author or dynasty or genre:
            t0 = time.perf_counter()
            merged = [
                d
                for d in merged
                if self._match_filter(d, author=author, dynasty=dynasty, genre=genre)
            ] or merged
            timings_ms["filter"] = round((time.perf_counter() - t0) * 1000, 1)

        t0 = time.perf_counter()
        if self.settings.rerank_enabled:
            docs, top_scores = self._rerank(query, merged)
        else:
            docs = merged[: self.settings.rerank_top_n]
            top_scores = []
        timings_ms["rerank"] = round((time.perf_counter() - t0) * 1000, 1)
        timings_ms["total"] = round(sum(timings_ms.values()), 1)

        if timings_ms["total"] >= 1000:
            logger.info("hybrid_retrieve slow: %s", timings_ms)

        update_run_metadata(
            doc_count=len(docs),
            vector_k=k,
            bm25_k=k,
            rerank_n=self.settings.rerank_top_n,
            filter_applied=bool(author or dynasty or genre),
            top_scores=top_scores,
            merged_candidates=len(merged),
            step_timings_ms=timings_ms,
            query=query[:200],
        )
        return docs

    def _match_filter(
        self,
        doc: Document,
        *,
        author: str | None,
        dynasty: str | None,
        genre: str | None,
    ) -> bool:
        meta = doc.metadata
        content = doc.page_content
        if author and author not in str(meta.get("author", "")) and author not in content:
            return False
        if dynasty and dynasty not in str(meta.get("dynasty", "")) and dynasty not in content:
            return False
        if genre and genre not in str(meta.get("genre", "")) and genre not in content:
            return False
        return True

    @traceable(run_type="retriever", name="bge_rerank")
    def _rerank(self, query: str, docs: list[Document]) -> tuple[list[Document], list[float]]:
        if not docs:
            return [], []

        settings = self.settings
        max_candidates = min(len(docs), settings.rerank_max_candidates)
        candidates = docs[:max_candidates]
        snippet_chars = min(settings.rerank_max_length * 2, 1024)
        pairs = [[query, _rerank_passage(d, snippet_chars)] for d in candidates]
        update_run_metadata(
            rerank_candidates=len(candidates),
            rerank_max_length=settings.rerank_max_length,
            rerank_snippet_chars=snippet_chars,
        )
        reranker = get_reranker()

        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=".*XLMRobertaTokenizerFast tokenizer.*",
                )
                t0 = time.perf_counter()
                scores = reranker.compute_score(
                    pairs,
                    batch_size=settings.rerank_batch_size,
                    max_length=settings.rerank_max_length,
                    normalize=True,
                )
                update_run_metadata(
                    rerank_compute_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
        except Exception as e:
            logger.warning("rerank compute_score failed, fallback to retrieval order: %s", e)
            return candidates[: settings.rerank_top_n], []
        if not isinstance(scores, list):
            scores = [scores]
        ranked = sorted(
            zip(candidates, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        top = ranked[: settings.rerank_top_n]
        top_scores = [round(float(s), 4) for _, s in ranked[:3]]
        return [d for d, _ in top], top_scores


@lru_cache
def get_hybrid_retriever() -> HybridRetriever:
    return HybridRetriever()


def format_context(docs: list[Document]) -> str:
    parts = []
    for i, d in enumerate(docs, 1):
        title = d.metadata.get("title", "未知")
        author = d.metadata.get("author", "")
        parts.append(f"[{i}] 《{title}》{author}\n{d.page_content[:1200]}")
    return "\n\n---\n\n".join(parts)

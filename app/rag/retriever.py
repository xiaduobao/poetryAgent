"""混合检索 + BGE Rerank。"""
from __future__ import annotations

import logging
import re
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Literal

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.observability.langsmith import traceable, update_run_metadata
from app.rag.chunker import load_poetry_documents, split_with_overlap
from app.rag.indexer import get_vector_store

logger = logging.getLogger(__name__)

_reranker = None
RRF_K = 60
RetrievalProfile = Literal["full", "light"]

PROFILE_DEFAULTS: dict[RetrievalProfile, dict[str, int | bool]] = {
    "full": {
        "retrieval_k": 0,  # 0 → settings.retrieval_top_k
        "rerank_n": 0,
        "rerank_max_candidates": 0,
        "skip_rerank": False,
    },
    "light": {
        "retrieval_k": 4,
        "rerank_n": 2,
        "rerank_max_candidates": 4,
        "skip_rerank": True,
    },
}


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
    """中文分词：优先 jieba，不可用时回退字+双字切分。"""
    try:
        import jieba

        return [t.strip() for t in jieba.cut(text) if t.strip()]
    except ImportError:
        chars = list(text)
        bigrams = [text[i : i + 2] for i in range(len(text) - 1)]
        return chars + bigrams


def _doc_key(doc: Document) -> str:
    source_file = doc.metadata.get("source_file")
    if source_file:
        return str(source_file)
    title = str(doc.metadata.get("title", "")).strip()
    author = str(doc.metadata.get("author", "")).strip()
    if title:
        return f"{title}|{author}"
    return doc.page_content[:200]


def _extract_poem_title(query: str) -> str | None:
    m = re.search(r"《([^》]+)》", query)
    if not m:
        return None
    title = m.group(1).strip()
    return title or None


def _build_chroma_filter(
    *,
    author: str | None,
    dynasty: str | None,
    genre: str | None,
) -> dict | None:
    """Chroma metadata 预过滤（精确匹配）。"""
    conditions: list[dict] = []
    if author:
        conditions.append({"author": {"$eq": author.strip()}})
    if dynasty:
        conditions.append({"dynasty": {"$eq": dynasty.strip()}})
    if genre:
        conditions.append({"genre": {"$eq": genre.strip()}})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _rrf_merge(
    vector_docs: list[Document],
    keyword_docs: list[Document],
    *,
    rrf_k: int = RRF_K,
) -> list[Document]:
    """Reciprocal Rank Fusion 合并向量与 BM25 结果。"""
    scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}

    for rank, doc in enumerate(vector_docs):
        key = _doc_key(doc)
        scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank + 1)
        doc_map[key] = doc

    for rank, doc in enumerate(keyword_docs):
        key = _doc_key(doc)
        scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank + 1)
        doc_map[key] = doc

    ranked_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
    return [doc_map[k] for k in ranked_keys]


def _prepend_priority(priority: list[Document], docs: list[Document]) -> list[Document]:
    """诗题短路等优先文档置于前列，按 doc_key 去重。"""
    seen: set[str] = set()
    merged: list[Document] = []
    for doc in priority + docs:
        key = _doc_key(doc)
        if key in seen:
            continue
        seen.add(key)
        merged.append(doc)
    return merged


class HybridRetriever:
    """向量检索 + BM25 关键词检索，RRF 融合后 Rerank。"""

    def __init__(self):
        self.settings = get_settings()
        self.vector_store = get_vector_store()
        chunks = split_with_overlap(
            load_poetry_documents(self.settings.corpus_dir)
        )
        self.corpus_docs = chunks
        tokenized = [_tokenize_zh(d.page_content) for d in chunks]
        self.bm25 = BM25Okapi(tokenized)

    @traceable(run_type="retriever", name="vector_search")
    def _vector_search(
        self,
        query: str,
        k: int,
        chroma_filter: dict | None,
    ) -> list[Document]:
        if chroma_filter:
            return self.vector_store.similarity_search(
                query,
                k=k,
                filter=chroma_filter,
            )
        return self.vector_store.similarity_search(query, k=k)

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

    @traceable(run_type="retriever", name="metadata_shortcut")
    def _metadata_shortcut(
        self,
        query: str,
        *,
        author: str | None,
        dynasty: str | None,
        genre: str | None,
    ) -> list[Document]:
        """诗题《》精确/包含匹配，短路提升召回。"""
        title = _extract_poem_title(query)
        if not title:
            return []

        matches: list[Document] = []
        for doc in self.corpus_docs:
            doc_title = str(doc.metadata.get("title", "")).strip()
            if not doc_title:
                continue
            if doc_title != title and title not in doc_title and doc_title not in title:
                continue
            if not self._match_filter(doc, author=author, dynasty=dynasty, genre=genre):
                continue
            matches.append(doc)

        update_run_metadata(shortcut_hits=len(matches), shortcut_title=title)
        return matches

    def _resolve_retrieval_params(
        self,
        profile: RetrievalProfile,
        *,
        retrieval_k: int | None,
        rerank_n: int | None,
        rerank_max_candidates: int | None,
        skip_rerank: bool | None,
    ) -> tuple[int, int, int, bool]:
        defaults = PROFILE_DEFAULTS[profile]
        settings = self.settings

        k = retrieval_k or defaults["retrieval_k"] or settings.retrieval_top_k
        n = rerank_n or defaults["rerank_n"] or settings.rerank_top_n
        max_c = (
            rerank_max_candidates
            or defaults["rerank_max_candidates"]
            or settings.rerank_max_candidates
        )
        skip = skip_rerank if skip_rerank is not None else bool(defaults["skip_rerank"])
        return int(k), int(n), int(max_c), skip

    @traceable(run_type="retriever", name="hybrid_retrieve")
    def retrieve(
        self,
        query: str,
        *,
        author: str | None = None,
        dynasty: str | None = None,
        genre: str | None = None,
        profile: RetrievalProfile = "full",
        retrieval_k: int | None = None,
        rerank_n: int | None = None,
        rerank_max_candidates: int | None = None,
        skip_rerank: bool | None = None,
    ) -> list[Document]:
        k, n, max_c, skip = self._resolve_retrieval_params(
            profile,
            retrieval_k=retrieval_k,
            rerank_n=rerank_n,
            rerank_max_candidates=rerank_max_candidates,
            skip_rerank=skip_rerank,
        )
        chroma_filter = _build_chroma_filter(author=author, dynasty=dynasty, genre=genre)
        timings_ms: dict[str, float] = {}

        t0 = time.perf_counter()
        shortcut_docs = self._metadata_shortcut(
            query,
            author=author,
            dynasty=dynasty,
            genre=genre,
        )
        timings_ms["shortcut"] = round((time.perf_counter() - t0) * 1000, 1)

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=2) as pool:
            vec_future = pool.submit(self._vector_search, query, k, chroma_filter)
            bm25_future = pool.submit(self._bm25_search, query, k)
            vector_docs = vec_future.result()
            keyword_docs = bm25_future.result()
        timings_ms["vector_bm25_parallel"] = round((time.perf_counter() - t0) * 1000, 1)

        t0 = time.perf_counter()
        merged = _rrf_merge(vector_docs, keyword_docs)
        merged = _prepend_priority(shortcut_docs, merged)
        timings_ms["merge"] = round((time.perf_counter() - t0) * 1000, 1)

        if author or dynasty or genre:
            t0 = time.perf_counter()
            filtered = [
                d
                for d in merged
                if self._match_filter(d, author=author, dynasty=dynasty, genre=genre)
            ]
            merged = filtered or merged
            timings_ms["filter"] = round((time.perf_counter() - t0) * 1000, 1)

        t0 = time.perf_counter()
        rerank_enabled = self.settings.rerank_enabled and not skip
        if rerank_enabled:
            docs, top_scores = self._rerank(
                query,
                merged,
                rerank_n=n,
                rerank_max_candidates=max_c,
            )
        else:
            docs = merged[:n]
            top_scores = []
        timings_ms["rerank"] = round((time.perf_counter() - t0) * 1000, 1)
        timings_ms["total"] = round(sum(timings_ms.values()), 1)

        if timings_ms["total"] >= 1000:
            logger.info("hybrid_retrieve slow: %s", timings_ms)

        update_run_metadata(
            doc_count=len(docs),
            retrieval_profile=profile,
            vector_k=k,
            bm25_k=k,
            rerank_n=n,
            skip_rerank=skip,
            chroma_filter=bool(chroma_filter),
            filter_applied=bool(author or dynasty or genre),
            top_scores=top_scores,
            merged_candidates=len(merged),
            shortcut_hits=len(shortcut_docs),
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
    def _rerank(
        self,
        query: str,
        docs: list[Document],
        *,
        rerank_n: int,
        rerank_max_candidates: int,
    ) -> tuple[list[Document], list[float]]:
        if not docs:
            return [], []

        settings = self.settings
        max_candidates = min(len(docs), rerank_max_candidates)
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
            return candidates[:rerank_n], []
        if not isinstance(scores, list):
            scores = [scores]
        ranked = sorted(
            zip(candidates, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        top = ranked[:rerank_n]
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

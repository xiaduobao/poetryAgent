"""混合检索 + BGE Rerank。"""
import logging
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
_reranker_disabled = False


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

    def _bm25_search(self, query: str, k: int) -> list[Document]:
        tokens = _tokenize_zh(query)
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:k]
        return [self.corpus_docs[i] for i in ranked if scores[i] > 0]

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
        vector_docs = self.vector_retriever.invoke(query)
        keyword_docs = self._bm25_search(query, k)
        merged = self._merge_docs(vector_docs, keyword_docs)

        if author or dynasty or genre:
            merged = [
                d
                for d in merged
                if self._match_filter(d, author=author, dynasty=dynasty, genre=genre)
            ] or merged

        docs, top_scores = self._rerank(query, merged)
        update_run_metadata(
            doc_count=len(docs),
            vector_k=k,
            bm25_k=k,
            rerank_n=self.settings.rerank_top_n,
            filter_applied=bool(author or dynasty or genre),
            top_scores=top_scores,
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

    def _rerank(self, query: str, docs: list[Document]) -> tuple[list[Document], list[float]]:
        if not docs:
            return [], []
        reranker = _get_reranker()
        if reranker is None:
            result = docs[: self.settings.rerank_top_n]
            return result, []

        pairs = [[query, d.page_content] for d in docs]
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=".*XLMRobertaTokenizerFast tokenizer.*",
                )
                scores = reranker.compute_score(pairs, normalize=True)
        except Exception as e:
            logger.warning("rerank compute_score failed, fallback to retrieval order: %s", e)
            return docs[: self.settings.rerank_top_n], []
        if not isinstance(scores, list):
            scores = [scores]
        ranked = sorted(
            zip(docs, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        top = ranked[: self.settings.rerank_top_n]
        top_scores = [round(float(s), 4) for _, s in ranked[:3]]
        return [d for d, _ in top], top_scores


def _get_reranker():
    global _reranker, _reranker_disabled
    if _reranker_disabled:
        return None
    if _reranker is not None:
        return _reranker
    settings = get_settings()
    if not settings.rerank_model.strip():
        _reranker_disabled = True
        return None
    try:
        from FlagEmbedding import FlagReranker

        from app.rag.embedder import resolve_model_path

        _reranker = FlagReranker(
            resolve_model_path(settings.rerank_model),
            use_fp16=False,
        )
    except Exception as e:
        logger.warning("rerank model load failed, skipping rerank: %s", e)
        _reranker = False  # type: ignore[assignment]
    return _reranker if _reranker is not False else None


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

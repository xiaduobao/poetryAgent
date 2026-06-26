"""混合检索单元测试（不依赖向量库）。"""
from __future__ import annotations

from langchain_core.documents import Document

from app.rag.retriever import (
    HybridRetriever,
    _doc_key,
    _extract_poem_title,
    _prepend_priority,
    _rrf_merge,
)


def test_rrf_merge_dedup_by_source_file():
    d1 = Document(page_content="相同内容" + "a" * 200, metadata={"source_file": "a.md"})
    d2 = Document(page_content="相同内容" + "a" * 200, metadata={"source_file": "a.md"})
    d3 = Document(page_content="不同内容", metadata={"source_file": "b.md"})
    merged = _rrf_merge([d1], [d2, d3])
    assert len(merged) == 2
    assert _doc_key(merged[0]) == "a.md"


def test_rrf_merge_prefers_both_lists():
    vec = Document(page_content="vector hit", metadata={"source_file": "v.md"})
    kw = Document(page_content="keyword hit", metadata={"source_file": "k.md"})
    merged = _rrf_merge([vec], [kw])
    assert len(merged) == 2
    assert {d.metadata["source_file"] for d in merged} == {"v.md", "k.md"}


def test_prepend_priority():
    priority = [Document(page_content="p", metadata={"source_file": "p.md"})]
    rest = [
        Document(page_content="p2", metadata={"source_file": "p.md"}),
        Document(page_content="r", metadata={"source_file": "r.md"}),
    ]
    out = _prepend_priority(priority, rest)
    assert len(out) == 2
    assert out[0].metadata["source_file"] == "p.md"


def test_extract_poem_title():
    assert _extract_poem_title("请赏析《春晓》") == "春晓"
    assert _extract_poem_title("李白是谁") is None


def test_metadata_shortcut():
    retriever = object.__new__(HybridRetriever)
    retriever.corpus_docs = [
        Document(
            page_content="# 《春晓》-孟浩然",
            metadata={"title": "春晓", "author": "孟浩然", "source_file": "chunxiao.md"},
        ),
        Document(
            page_content="# 《登高》-杜甫",
            metadata={"title": "登高", "author": "杜甫", "source_file": "denggao.md"},
        ),
    ]
    hits = retriever._metadata_shortcut("赏析《春晓》", author="孟浩然", dynasty=None, genre=None)
    assert len(hits) == 1
    assert hits[0].metadata["title"] == "春晓"


def test_doc_key_prefers_source_file():
    doc = Document(page_content="x", metadata={"source_file": "f.md", "title": "春晓"})
    assert _doc_key(doc) == "f.md"

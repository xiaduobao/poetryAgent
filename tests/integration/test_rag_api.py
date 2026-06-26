"""RAG 检索 smoke 测试（Mock 向量库）。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document


@pytest.mark.asyncio
@patch("app.api.routes.get_hybrid_retriever")
async def test_rag_endpoint_returns_documents(mock_get, client, auth_headers):
    doc = Document(
        page_content="春眠不觉晓，处处闻啼鸟。",
        metadata={"author": "孟浩然", "title": "春晓"},
    )
    retriever = MagicMock()
    retriever.retrieve.return_value = [doc]
    mock_get.return_value = retriever

    resp = await client.post(
        "/api/v1/rag",
        headers=auth_headers,
        json={"query": "春天的诗", "author": "孟浩然"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "春天的诗"
    assert len(body["documents"]) == 1
    assert "春眠" in body["documents"][0]["content"]


def test_hybrid_retriever_rrf_dedup():
    from app.rag.retriever import _rrf_merge

    d1 = Document(page_content="相同内容" + "a" * 200, metadata={"source_file": "same.md"})
    d2 = Document(page_content="相同内容" + "a" * 200, metadata={"source_file": "same.md"})
    d3 = Document(page_content="不同内容", metadata={"source_file": "other.md"})
    merged = _rrf_merge([d1], [d2, d3])
    assert len(merged) == 2

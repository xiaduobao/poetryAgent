"""Chat API 集成测试（Mock Agent，不调用 LLM）。"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@patch("app.api.routes._traced_run_agent")
async def test_chat_records_answer(mock_run, client: AsyncClient, auth_headers: dict[str, str]):
    mock_run.return_value = {
        "answer": "这是测试回答",
        "intent": "rag",
        "rag_context": "上下文",
        "sources": [],
        "tokens_used": 42,
    }

    resp = await client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"message": "请赏析《春晓》", "thread_id": "default"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] == "这是测试回答"
    assert body["intent"] == "rag"
    mock_run.assert_called_once()

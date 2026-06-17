"""Chat API 集成测试（Mock Agent，不调用 LLM）。"""
from __future__ import annotations

import base64
from unittest.mock import patch

import pytest
from httpx import AsyncClient

_TINY_PNG_B64 = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
).decode("ascii")


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


@pytest.mark.asyncio
@patch("app.api.routes.describe_image_for_poetry", return_value="远山含黛，孤舟江上")
@patch("app.api.routes._traced_run_agent")
async def test_chat_with_image(mock_run, mock_vision, client: AsyncClient, auth_headers: dict[str, str]):
    mock_run.return_value = {
        "answer": "江上孤舟",
        "intent": "tool_writing",
        "rag_context": "",
        "sources": [],
        "tokens_used": 100,
    }

    resp = await client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"message": "", "image_base64": _TINY_PNG_B64, "thread_id": "default"},
    )
    assert resp.status_code == 200, resp.text
    mock_vision.assert_called_once()
    agent_message = mock_run.call_args[0][0]
    assert agent_message.startswith("【看图创作】")
    assert "远山含黛" in agent_message

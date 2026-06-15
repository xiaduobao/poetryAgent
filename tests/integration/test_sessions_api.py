"""会话 API 集成测试。"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_session_crud(client: AsyncClient, auth_headers: dict[str, str]):
    create = await client.post("/api/v1/sessions", headers=auth_headers, json={"title": "测试会话"})
    assert create.status_code == 200
    session = create.json()
    session_id = session["id"]
    assert session["title"] == "测试会话"

    listing = await client.get("/api/v1/sessions", headers=auth_headers)
    assert listing.status_code == 200
    assert any(s["id"] == session_id for s in listing.json())

    rename = await client.patch(
        f"/api/v1/sessions/{session_id}",
        headers=auth_headers,
        json={"title": "已重命名"},
    )
    assert rename.status_code == 200
    assert rename.json()["title"] == "已重命名"

    delete = await client.delete(f"/api/v1/sessions/{session_id}", headers=auth_headers)
    assert delete.status_code == 204

    missing = await client.get(f"/api/v1/sessions/{session_id}", headers=auth_headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_sessions_require_auth(client: AsyncClient):
    resp = await client.get("/api/v1/sessions")
    assert resp.status_code == 401

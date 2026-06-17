"""Pytest 共享 fixtures。"""
from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings


@pytest.fixture
async def client(tmp_path, monkeypatch) -> AsyncIterator[AsyncClient]:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("SESSIONS_DB", str(db_path))
    monkeypatch.setenv("JWT_SECRET_KEY", "ci-test-secret-key-for-pytest")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-placeholder")
    get_settings.cache_clear()

    import app.db.database as db_module

    db_module._engine = None
    db_module._session_factory = None

    with (
        patch("app.main.build_vector_store"),
        patch("app.main.setup_checkpointer", new_callable=AsyncMock),
    ):
        from app.main import create_app

        app = create_app()
        transport = ASGITransport(app=app, lifespan="on")
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    get_settings.cache_clear()
    db_module._engine = None
    db_module._session_factory = None


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = "pytest@example.com"
    password = "password123"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

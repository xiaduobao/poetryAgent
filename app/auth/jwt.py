"""JWT 签发与校验。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.config import get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    expire = _utcnow() + timedelta(minutes=settings.jwt_access_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "type": "access", "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_guest_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    expire = _utcnow() + timedelta(hours=settings.guest_access_expire_hours)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": "access",
        "exp": expire,
        "role": "guest",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> tuple[str, datetime]:
    settings = get_settings()
    expire = _utcnow() + timedelta(days=settings.jwt_refresh_expire_days)
    payload = {"sub": subject, "type": "refresh", "exp": expire}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expire


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def verify_access_token(token: str) -> str | None:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None


def verify_refresh_token(token: str) -> str | None:
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            return None
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None

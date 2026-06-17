"""API 限流（slowapi），用于控制 LLM 调用频率与成本。"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth.jwt import verify_access_token
from app.config import get_settings


def get_client_ip(request: Request) -> str:
    """优先使用反向代理透传的真实 IP。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return get_remote_address(request)


def get_rate_limit_key(request: Request) -> str:
    """优先按用户 ID 限流，未登录则按 IP。"""
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        uid = verify_access_token(token)
        if uid:
            request.state.user_id = uid
            return f"user:{uid}"
    return f"ip:{get_client_ip(request)}"


def create_limiter() -> Limiter:
    settings = get_settings()
    default_limits = [settings.rate_limit_default] if settings.rate_limit_default else []
    return Limiter(
        key_func=get_rate_limit_key,
        default_limits=default_limits,
        enabled=settings.rate_limit_enabled,
        storage_uri=settings.rate_limit_storage_uri or None,
    )


limiter = create_limiter()

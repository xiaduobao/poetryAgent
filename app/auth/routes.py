"""认证路由：注册、登录、刷新、登出。"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import (
    create_access_token,
    create_guest_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from app.auth.password import hash_password, verify_password
from app.auth.schemas import (
    GuestTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.config import get_settings
from app.db import crud
from app.db.audit import log_audit
from app.db.database import get_db
from app.db.models import RefreshToken, Subscription, Tenant, User
from app.security.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().rate_limit_default)
async def register(
    request: Request,
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == req.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    tenant = Tenant(name=f"{req.email.split('@')[0]} 的工作区")
    db.add(tenant)
    await db.flush()

    subscription = Subscription(tenant_id=tenant.id, plan="free")
    db.add(subscription)

    user = User(
        email=req.email.lower(),
        password_hash=hash_password(req.password),
        tenant_id=tenant.id,
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token(user.id, {"tenant_id": user.tenant_id, "role": user.role})
    refresh_token, expires_at = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_refresh_token(refresh_token),
            expires_at=expires_at,
        )
    )
    await log_audit(
        db,
        action="user.register",
        user_id=user.id,
        tenant_id=user.tenant_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="账户已禁用")

    access_token = create_access_token(user.id, {"tenant_id": user.tenant_id, "role": user.role})
    refresh_token, expires_at = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_refresh_token(refresh_token),
            expires_at=expires_at,
        )
    )
    await log_audit(
        db,
        action="user.login",
        user_id=user.id,
        tenant_id=user.tenant_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/guest", response_model=GuestTokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def guest_login(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    if not settings.guest_enabled:
        raise HTTPException(status_code=403, detail="游客访问未开启")

    guest_id = str(uuid.uuid4())
    tenant = Tenant(name="游客工作区")
    db.add(tenant)
    await db.flush()

    subscription = Subscription(
        tenant_id=tenant.id,
        plan="guest",
        daily_chat_limit=settings.guest_daily_chat_limit,
        daily_rag_limit=settings.guest_daily_rag_limit,
    )
    db.add(subscription)

    user = User(
        email=f"guest-{guest_id}@guest.local",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role="guest",
        tenant_id=tenant.id,
    )
    db.add(user)
    await db.flush()

    access_token = create_guest_access_token(
        user.id,
        {"tenant_id": user.tenant_id, "role": "guest"},
    )
    await log_audit(
        db,
        action="user.guest",
        user_id=user.id,
        tenant_id=user.tenant_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return GuestTokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    user_id = verify_refresh_token(req.refresh_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="刷新令牌无效或已过期")

    token_hash = _hash_refresh_token(req.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
        )
    )
    stored = result.scalar_one_or_none()
    if not stored or stored.user_id != user_id:
        raise HTTPException(status_code=401, detail="刷新令牌无效或已吊销")

    stored.revoked = True

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    access_token = create_access_token(user.id, {"tenant_id": user.tenant_id, "role": user.role})
    new_refresh, expires_at = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_refresh_token(new_refresh),
            expires_at=expires_at,
        )
    )
    await db.flush()
    return TokenResponse(access_token=access_token, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    req: RefreshRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token_hash = _hash_refresh_token(req.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user.id,
        )
    )
    stored = result.scalar_one_or_none()
    if stored:
        stored.revoked = True
    await log_audit(
        db,
        action="user.logout",
        user_id=user.id,
        tenant_id=user.tenant_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    sub = await crud.get_subscription(db, user.tenant_id)
    is_guest = user.role == "guest"
    return UserOut(
        id=user.id,
        email="游客" if is_guest else user.email,
        role=user.role,
        tenant_id=user.tenant_id,
        plan=sub.plan if sub else "free",
        is_guest=is_guest,
        created_at=user.created_at,
    )

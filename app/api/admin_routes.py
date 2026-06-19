"""管理后台 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_admin
from app.db import crud
from app.db.audit import log_audit
from app.db.database import get_db
from app.db.models import AuditLog, UsageRecord, User

router = APIRouter(prefix="/admin", tags=["admin"])


class SubscriptionUpdate(BaseModel):
    plan: str | None = None
    daily_chat_limit: int | None = Field(default=None, ge=1)
    daily_rag_limit: int | None = Field(default=None, ge=1)
    llm_model: str | None = None
    rag_top_k: int | None = Field(default=None, ge=1, le=10)
    status: str | None = None


class UserStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|disabled)$")


@router.get("/users")
async def list_users(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()).limit(200))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "status": u.status,
            "tenant_id": u.tenant_id,
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    req: UserStatusUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.status = req.status
    await log_audit(
        db,
        action="admin.user_status_update",
        user_id=admin.id,
        tenant_id=admin.tenant_id,
        resource_type="user",
        resource_id=user_id,
        detail=req.status,
    )
    return {"id": user.id, "status": user.status}


@router.get("/subscriptions/{tenant_id}")
async def get_subscription(
    tenant_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    sub = await crud.get_subscription(db, tenant_id)
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return {
        "tenant_id": sub.tenant_id,
        "plan": sub.plan,
        "status": sub.status,
        "daily_chat_limit": sub.daily_chat_limit,
        "daily_rag_limit": sub.daily_rag_limit,
        "llm_model": sub.llm_model,
        "rag_top_k": sub.rag_top_k,
    }


@router.patch("/subscriptions/{tenant_id}")
async def update_subscription(
    tenant_id: str,
    req: SubscriptionUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    sub = await crud.get_subscription(db, tenant_id)
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(sub, field, value)
    await log_audit(
        db,
        action="admin.subscription_update",
        user_id=admin.id,
        tenant_id=admin.tenant_id,
        resource_type="subscription",
        resource_id=tenant_id,
    )
    return {"tenant_id": sub.tenant_id, "plan": sub.plan, "status": sub.status}


@router.get("/usage/summary")
async def usage_summary(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UsageRecord.action, func.count(UsageRecord.id)).group_by(UsageRecord.action)
    )
    by_action = {row[0]: row[1] for row in result.all()}
    token_result = await db.execute(select(func.sum(UsageRecord.tokens)))
    total_tokens = int(token_result.scalar_one() or 0)
    return {"by_action": by_action, "total_tokens": total_tokens}


@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = 100,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "tenant_id": log.tenant_id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "ip_address": log.ip_address,
            "detail": log.detail,
            "created_at": log.created_at,
        }
        for log in logs
    ]

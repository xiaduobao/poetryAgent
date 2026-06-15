"""套餐配额校验依赖。"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.database import get_db
from app.db.models import User


async def require_chat_quota(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    ok, msg = await crud.check_quota(db, user.tenant_id, "chat")
    if not ok:
        raise HTTPException(status_code=429, detail=msg)
    return user


async def require_rag_quota(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    ok, msg = await crud.check_quota(db, user.tenant_id, "rag")
    if not ok:
        raise HTTPException(status_code=429, detail=msg)
    return user

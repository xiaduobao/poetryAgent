"""会话 CRUD 路由。"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import clear_thread_checkpoint
from app.api.schemas import (
    MessageOut,
    SessionCreateRequest,
    SessionDetailOut,
    SessionOut,
    SessionRenameRequest,
)
from app.auth.dependencies import get_current_user
from app.db import crud
from app.db.audit import log_audit
from app.db.database import get_db
from app.db.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await crud.list_sessions(db, user.id, q=q)


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    req: SessionCreateRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    title = req.title if req else "新对话"
    return await crud.create_session(db, user.id, title=title)


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await crud.get_session(db, session_id, user_id=user.id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionDetailOut(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[MessageOut.model_validate(m) for m in session.messages],
    )


@router.patch("/{session_id}", response_model=SessionOut)
async def rename_session(
    session_id: str,
    req: SessionRenameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await crud.rename_session(db, session_id, user.id, req.title)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    request: Request,
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await crud.delete_session(db, session_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    await log_audit(
        db,
        action="session.delete",
        user_id=user.id,
        tenant_id=user.tenant_id,
        resource_type="session",
        resource_id=session_id,
        ip_address=request.client.host if request.client else None,
    )
    try:
        clear_thread_checkpoint(session_id)
    except Exception:
        logger.warning("Failed to clear checkpoint for %s", session_id)

"""会话 CRUD 路由。"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import clear_thread_checkpoint
from app.api.schemas import (
    SessionCreateRequest,
    SessionDetailOut,
    SessionOut,
    SessionRenameRequest,
    MessageOut,
)
from app.db import crud
from app.db.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionOut])
async def list_sessions(q: str | None = None, db: AsyncSession = Depends(get_db)):
    sessions = await crud.list_sessions(db, q=q)
    return sessions


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    req: SessionCreateRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    title = req.title if req else "新对话"
    session = await crud.create_session(db, title=title)
    return session


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await crud.get_session(db, session_id)
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
    db: AsyncSession = Depends(get_db),
):
    session = await crud.rename_session(db, session_id, req.title)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    deleted = await crud.delete_session(db, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    try:
        clear_thread_checkpoint(session_id)
    except Exception:
        logger.warning("Failed to clear checkpoint for %s", session_id)

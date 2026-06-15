"""会话与消息 CRUD。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ChatSession, Message

DEFAULT_TITLE = "新对话"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def create_session(db: AsyncSession, title: str = DEFAULT_TITLE) -> ChatSession:
    session = ChatSession(title=title)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def get_session(db: AsyncSession, session_id: str) -> ChatSession | None:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages))
    )
    return result.scalar_one_or_none()


async def list_sessions(db: AsyncSession, q: str | None = None) -> list[ChatSession]:
    stmt = select(ChatSession).order_by(ChatSession.updated_at.desc())
    if q and q.strip():
        keyword = f"%{q.strip()}%"
        stmt = (
            select(ChatSession)
            .join(Message, Message.session_id == ChatSession.id, isouter=True)
            .where(
                or_(
                    ChatSession.title.ilike(keyword),
                    Message.content.ilike(keyword),
                )
            )
            .distinct()
            .order_by(ChatSession.updated_at.desc())
        )
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


async def rename_session(
    db: AsyncSession, session_id: str, title: str
) -> ChatSession | None:
    session = await get_session(db, session_id)
    if not session:
        return None
    session.title = title.strip() or DEFAULT_TITLE
    session.updated_at = _utcnow()
    await db.flush()
    return session


async def delete_session(db: AsyncSession, session_id: str) -> bool:
    session = await get_session(db, session_id)
    if not session:
        return False
    await db.delete(session)
    await db.flush()
    return True


async def add_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    intent: str | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> Message | None:
    session = await get_session(db, session_id)
    if not session:
        return None
    sources_json = json.dumps(sources, ensure_ascii=False) if sources else None
    msg = Message(
        session_id=session_id,
        role=role,
        content=content,
        intent=intent,
        sources_json=sources_json,
    )
    db.add(msg)
    session.updated_at = _utcnow()
    await db.flush()
    await db.refresh(msg)
    return msg


async def auto_title_from_message(
    db: AsyncSession, session_id: str, user_text: str
) -> None:
    session = await get_session(db, session_id)
    if not session or session.title != DEFAULT_TITLE:
        return
    title = user_text.strip().replace("\n", " ")[:20]
    if title:
        session.title = title
        session.updated_at = _utcnow()
        await db.flush()

"""会话与消息 CRUD。"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ChatSession, Message, Subscription, UsageRecord

DEFAULT_TITLE = "新对话"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today_start() -> datetime:
    today = date.today()
    return datetime(today.year, today.month, today.day, tzinfo=timezone.utc)


async def create_session(
    db: AsyncSession, user_id: str, title: str = DEFAULT_TITLE
) -> ChatSession:
    session = ChatSession(user_id=user_id, title=title)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def get_session(
    db: AsyncSession, session_id: str, user_id: str | None = None
) -> ChatSession | None:
    stmt = (
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages))
    )
    if user_id:
        stmt = stmt.where(ChatSession.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_sessions(
    db: AsyncSession, user_id: str, q: str | None = None
) -> list[ChatSession]:
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    if q and q.strip():
        keyword = f"%{q.strip()}%"
        stmt = (
            select(ChatSession)
            .join(Message, Message.session_id == ChatSession.id, isouter=True)
            .where(
                ChatSession.user_id == user_id,
                or_(
                    ChatSession.title.ilike(keyword),
                    Message.content.ilike(keyword),
                ),
            )
            .distinct()
            .order_by(ChatSession.updated_at.desc())
        )
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


async def rename_session(
    db: AsyncSession, session_id: str, user_id: str, title: str
) -> ChatSession | None:
    session = await get_session(db, session_id, user_id=user_id)
    if not session:
        return None
    session.title = title.strip() or DEFAULT_TITLE
    session.updated_at = _utcnow()
    await db.flush()
    return session


async def delete_session(db: AsyncSession, session_id: str, user_id: str) -> bool:
    session = await get_session(db, session_id, user_id=user_id)
    if not session:
        return False
    await db.delete(session)
    await db.flush()
    return True


async def add_message(
    db: AsyncSession,
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    intent: str | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> Message | None:
    session = await get_session(db, session_id, user_id=user_id)
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
    db: AsyncSession, session_id: str, user_id: str, user_text: str
) -> None:
    session = await get_session(db, session_id, user_id=user_id)
    if not session or session.title != DEFAULT_TITLE:
        return
    title = user_text.strip().replace("\n", " ")[:20]
    if title:
        session.title = title
        session.updated_at = _utcnow()
        await db.flush()


async def get_subscription(db: AsyncSession, tenant_id: str) -> Subscription | None:
    result = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def count_daily_usage(
    db: AsyncSession, tenant_id: str, action: str
) -> int:
    result = await db.execute(
        select(func.count(UsageRecord.id)).where(
            UsageRecord.tenant_id == tenant_id,
            UsageRecord.action == action,
            UsageRecord.created_at >= _today_start(),
        )
    )
    return int(result.scalar_one() or 0)


async def record_usage(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    action: str,
    tokens: int = 0,
) -> UsageRecord:
    record = UsageRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        tokens=tokens,
    )
    db.add(record)
    await db.flush()
    return record


async def check_quota(db: AsyncSession, tenant_id: str, action: str) -> tuple[bool, str]:
    sub = await get_subscription(db, tenant_id)
    if not sub:
        return True, ""
    used = await count_daily_usage(db, tenant_id, action)
    if action == "chat" and used >= sub.daily_chat_limit:
        return False, f"今日对话次数已达上限（{sub.daily_chat_limit} 次）"
    if action == "rag" and used >= sub.daily_rag_limit:
        return False, f"今日检索次数已达上限（{sub.daily_rag_limit} 次）"
    return True, ""

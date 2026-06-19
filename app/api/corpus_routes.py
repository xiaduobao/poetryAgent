"""语料管理 API。"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.db.audit import log_audit
from app.db.database import get_db
from app.db.models import CorpusDocument, User
from app.rag.indexer import build_vector_store

router = APIRouter(prefix="/corpus", tags=["corpus"])

_SAFE_FILENAME = re.compile(r"^[\w\u4e00-\u9fff\-《》·]+\.md$", re.UNICODE)


class CorpusOut(BaseModel):
    id: str
    filename: str
    status: str
    error_message: str | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CorpusOut])
async def list_corpus(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CorpusDocument)
        .where(CorpusDocument.tenant_id == user.tenant_id)
        .order_by(CorpusDocument.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/upload", response_model=CorpusOut, status_code=201)
async def upload_corpus(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not _SAFE_FILENAME.match(file.filename):
        raise HTTPException(status_code=400, detail="文件名须为 .md 且仅含安全字符")

    content = await file.read()
    if len(content) > 512_000:
        raise HTTPException(status_code=400, detail="文件过大（最大 512KB）")
    if not content.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    settings = get_settings()
    corpus_dir = Path(settings.corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    dest = corpus_dir / file.filename

    doc = CorpusDocument(
        tenant_id=user.tenant_id,
        user_id=user.id,
        filename=file.filename,
        status="processing",
    )
    db.add(doc)
    await db.flush()

    try:
        dest.write_bytes(content)
        build_vector_store(force=True)
        doc.status = "indexed"
    except Exception as e:
        doc.status = "failed"
        doc.error_message = str(e)[:500]
        if dest.exists():
            dest.unlink(missing_ok=True)

    await log_audit(
        db,
        action="corpus.upload",
        user_id=user.id,
        tenant_id=user.tenant_id,
        resource_type="corpus",
        resource_id=doc.id,
        detail=file.filename,
    )
    await db.flush()
    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_corpus(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CorpusDocument).where(
            CorpusDocument.id == doc_id,
            CorpusDocument.tenant_id == user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    settings = get_settings()
    path = Path(settings.corpus_dir) / doc.filename
    if path.exists():
        path.unlink()
    await db.delete(doc)
    try:
        build_vector_store(force=True)
    except Exception:
        pass
    await log_audit(
        db,
        action="corpus.delete",
        user_id=user.id,
        tenant_id=user.tenant_id,
        resource_type="corpus",
        resource_id=doc_id,
    )

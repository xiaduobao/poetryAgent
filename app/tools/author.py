"""作者生平查询工具。"""
import json
from pathlib import Path
from typing import Any

from app.config import get_settings


def _load_authors() -> dict[str, Any]:
    path = Path(get_settings().authors_db)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def query_author(name: str) -> dict[str, Any]:
    """根据作者名查询生平、代表作、风格。"""
    db = _load_authors()
    # 精确或包含匹配
    if name in db:
        return {"found": True, "data": db[name]}
    for key, val in db.items():
        if name in key or key in name:
            return {"found": True, "data": val}
    return {
        "found": False,
        "message": f"知识库中暂无「{name}」的生平资料，可尝试 RAG 检索相关诗词。",
    }

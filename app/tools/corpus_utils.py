"""语料 Markdown 解析辅助。"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from langchain_core.documents import Document

from app.config import get_settings
from app.rag.chunker import load_poetry_documents


def _extract_section(content: str, heading: str) -> str:
    pattern = rf"##\s*{re.escape(heading)}\s*\n(.*?)(?:\n##|\Z)"
    m = re.search(pattern, content, re.DOTALL)
    return m.group(1).strip() if m else ""


def parse_poem_doc(doc: Document) -> dict[str, Any]:
    """从语料 Document 解析结构化字段。"""
    content = doc.page_content
    meta = doc.metadata
    theme = meta.get("主题") or meta.get("theme") or ""
    if not theme:
        meta_section = _extract_section(content, "元数据")
        for line in meta_section.splitlines():
            if "主题" in line:
                theme = line.split("：", 1)[-1].split(":", 1)[-1].strip().lstrip("-").strip()
                break

    return {
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "dynasty": meta.get("dynasty", ""),
        "genre": meta.get("genre", ""),
        "theme": theme,
        "original": _extract_section(content, "原文"),
        "notes": _extract_section(content, "注释"),
        "translation": _extract_section(content, "白话译文"),
        "appreciation": _extract_section(content, "鉴赏"),
        "source_file": meta.get("source_file", ""),
        "page_content": content,
    }


@lru_cache
def get_corpus_documents() -> tuple[Document, ...]:
    return tuple(load_poetry_documents(get_settings().corpus_dir))


def get_parsed_corpus() -> list[dict[str, Any]]:
    return [parse_poem_doc(d) for d in get_corpus_documents()]


def normalize_title(text: str) -> str:
    return re.sub(r"[《》\s]", "", text.strip())

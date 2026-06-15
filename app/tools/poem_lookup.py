"""诗词检索工具：按诗题/作者查找原文与注释。"""
from __future__ import annotations

from typing import Any

from app.tools.corpus_utils import get_parsed_corpus, normalize_title


def _score_match(poem: dict[str, Any], title: str, author: str) -> int:
    score = 0
    poem_title = normalize_title(poem.get("title", ""))
    poem_author = poem.get("author", "")
    query_title = normalize_title(title)
    query_author = author.strip()

    if query_title:
        if query_title == poem_title:
            score += 10
        elif query_title in poem_title or poem_title in query_title:
            score += 6
        elif query_title in poem.get("page_content", ""):
            score += 2

    if query_author:
        if query_author == poem_author:
            score += 8
        elif query_author in poem_author or poem_author in query_author:
            score += 4

    if not query_title and not query_author:
        return 0
    if query_title and not query_author:
        return score
    if query_author and not query_title:
        return score if score > 0 else (4 if query_author in poem_author else 0)
    return score


def lookup_poem(title: str = "", author: str = "") -> dict[str, Any]:
    """按诗题和/或作者检索诗词。"""
    title = title.strip()
    author = author.strip()
    if not title and not author:
        return {
            "found": False,
            "message": "请提供诗题或作者名。",
        }

    scored: list[tuple[int, dict[str, Any]]] = []
    for poem in get_parsed_corpus():
        score = _score_match(poem, title, author)
        if score > 0:
            scored.append((score, poem))

    if not scored:
        return {
            "found": False,
            "message": f"知识库中未找到「{title or author}」相关诗词。",
        }

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]

    if len(scored) > 1 and scored[1][0] == best_score:
        candidates = [
            {
                "title": p["title"],
                "author": p["author"],
                "dynasty": p["dynasty"],
                "source_file": p["source_file"],
            }
            for _, p in scored[:5]
        ]
        return {
            "found": True,
            "ambiguous": True,
            "candidates": candidates,
            "message": "找到多个匹配结果，请指定更精确的诗题。",
        }

    return {
        "found": True,
        "data": {
            "title": best["title"],
            "author": best["author"],
            "dynasty": best["dynasty"],
            "genre": best["genre"],
            "theme": best["theme"],
            "original": best["original"],
            "notes": best["notes"],
            "translation": best["translation"],
            "source_file": best["source_file"],
        },
    }

"""典故释义工具：解释诗句中的典故、地名等。"""
from __future__ import annotations

from typing import Any

from app.rag.retriever import get_hybrid_retriever
from app.tools.corpus_utils import get_parsed_corpus, parse_poem_doc


def _parse_note_lines(notes: str) -> list[tuple[str, str]]:
    """解析注释行，返回 (关键词, 解释) 列表。"""
    pairs: list[tuple[str, str]] = []
    for line in notes.splitlines():
        line = line.strip().lstrip("-").strip()
        if not line:
            continue
        if "：" in line:
            key, val = line.split("：", 1)
        elif ":" in line:
            key, val = line.split(":", 1)
        else:
            continue
        key = key.strip().strip("：:").strip()
        val = val.strip()
        if key and val:
            pairs.append((key, val))
    return pairs


def _search_notes(query: str, poem: dict[str, Any]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    notes = poem.get("notes", "")
    if not notes:
        return matches

    for key, explanation in _parse_note_lines(notes):
        if query in key or key in query or query in explanation:
            matches.append(
                {
                    "allusion": key,
                    "explanation": explanation,
                    "source_poem": f"《{poem.get('title', '')}》",
                    "source_file": poem.get("source_file", ""),
                }
            )

    if not matches and query in notes:
        for key, explanation in _parse_note_lines(notes):
            matches.append(
                {
                    "allusion": key,
                    "explanation": explanation,
                    "source_poem": f"《{poem.get('title', '')}》",
                    "source_file": poem.get("source_file", ""),
                }
            )
            if len(matches) >= 3:
                break

    return matches


def explain_allusion(query: str) -> dict[str, Any]:
    """解释诗句片段或典故名。"""
    query = query.strip()
    if not query:
        return {"found": False, "message": "请提供诗句片段或典故名。"}

    matches: list[dict[str, Any]] = []
    for poem in get_parsed_corpus():
        matches.extend(_search_notes(query, poem))
        if len(matches) >= 5:
            break

    if not matches:
        try:
            retriever = get_hybrid_retriever()
            docs = retriever.retrieve(query)[:3]
            for doc in docs:
                poem = parse_poem_doc(doc)
                poem_matches = _search_notes(query, poem)
                if not poem_matches:
                    notes = poem.get("notes", "")
                    if query in notes:
                        for key, explanation in _parse_note_lines(notes):
                            if query in key or query in explanation:
                                poem_matches.append(
                                    {
                                        "allusion": key,
                                        "explanation": explanation,
                                        "source_poem": f"《{poem.get('title', '')}》",
                                        "source_file": poem.get("source_file", ""),
                                    }
                                )
                matches.extend(poem_matches)
                if len(matches) >= 5:
                    break
        except Exception:
            pass

    if not matches:
        return {
            "found": False,
            "query": query,
            "message": f"资料库中暂无「{query}」的典故注释，请尝试更具体的关键词。",
        }

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for m in matches:
        key = f"{m['allusion']}:{m['source_file']}"
        if key not in seen:
            seen.add(key)
            unique.append(m)

    return {
        "found": True,
        "query": query,
        "matches": unique[:5],
    }

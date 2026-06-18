"""从 Agent 准备状态构建引用来源列表。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agent.graph import PreparedAgent


def _snippet(text: str, max_len: int = 200) -> str:
    text = (text or "").strip()
    return text[:max_len] + ("…" if len(text) > max_len else "")


def _sources_from_tool_result(tool_result: str, intent: str) -> list[dict[str, Any]]:
    if not tool_result:
        return []

    data: dict[str, Any] | None = None
    for line in tool_result.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            break
        except json.JSONDecodeError:
            continue

    if data is None:
        try:
            data = json.loads(tool_result)
        except json.JSONDecodeError:
            return []

    sources: list[dict[str, Any]] = []

    if intent == "tool_lookup":
        if data.get("ambiguous") and data.get("candidates"):
            for c in data["candidates"]:
                sources.append(
                    {
                        "title": c.get("title"),
                        "author": c.get("author"),
                        "source_file": c.get("source_file"),
                    }
                )
        elif data.get("data"):
            d = data["data"]
            sources.append(
                {
                    "title": d.get("title"),
                    "author": d.get("author"),
                    "snippet": _snippet(d.get("original", "")),
                    "source_file": d.get("source_file"),
                }
            )
    elif intent == "tool_theme" and data.get("recommendations"):
        for r in data["recommendations"]:
            sources.append(
                {
                    "title": r.get("title"),
                    "author": r.get("author"),
                    "snippet": _snippet(r.get("snippet", "")),
                    "source_file": r.get("source_file"),
                }
            )
    elif intent == "tool_allusion" and data.get("matches"):
        for m in data["matches"]:
            sources.append(
                {
                    "title": m.get("source_poem", "").strip("《》"),
                    "snippet": _snippet(f"{m.get('allusion', '')}：{m.get('explanation', '')}"),
                    "source_file": m.get("source_file"),
                }
            )
    elif intent == "tool_writing" and data.get("references"):
        for r in data["references"]:
            sources.append(
                {
                    "title": r.get("title"),
                    "author": r.get("author"),
                    "snippet": _snippet(r.get("snippet", "")),
                    "source_file": r.get("source_file"),
                }
            )
    elif intent == "tool_meter" and data.get("found"):
        sources.append(
            {
                "title": data.get("title"),
                "snippet": _snippet("\n".join(data.get("lines", [])[:2])),
            }
        )

    return [s for s in sources if any(s.values())]


def build_sources_from_prepared(prepared: PreparedAgent) -> list[dict[str, Any]]:
    """从 prepared agent 状态提取前端可展示的引用来源。"""
    state = prepared["state"]
    mode = prepared["mode"]
    intent = prepared["intent"]

    if mode == "rag":
        return list(state.get("source_refs") or [])

    if mode == "compound_synthesis":
        return list(state.get("source_refs") or [])

    if mode == "tool_summary":
        refs = _sources_from_tool_result(state.get("tool_result") or "", intent)
        if refs:
            return refs
        return list(state.get("source_refs") or [])

    return []

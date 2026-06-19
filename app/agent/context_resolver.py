"""从对话历史中解析指代性提问（「这首诗」等）的诗词上下文。"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.security.filter import strip_user_input

_POEM_TITLE = re.compile(r"《([^》]+)》")
_JSON_TITLE = re.compile(r'"title"\s*:\s*"([^"\\]+)"')
_ANAPHORA = re.compile(
    r"(这首诗|此诗|该诗|这首词|此词|该词|上面(?:那)?(?:首)?诗|刚才(?:那)?(?:首)?诗|上文(?:的)?诗|刚才(?:提到|说的)?(?:的)?诗)"
)
_FAMOUS_POEMS = ("静夜思", "登高", "念奴娇", "赤壁", "枫桥夜泊", "春望", "春晓")


def needs_poem_context(query: str) -> bool:
    """当前问句是否在指代上文诗词且未自带书名号诗题。"""
    clean = strip_user_input(query)
    if _POEM_TITLE.search(clean):
        return False
    return _ANAPHORA.search(clean) is not None


def _message_text(msg: BaseMessage) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    return str(content)


def _title_from_text(text: str) -> str | None:
    match = _POEM_TITLE.search(text)
    if match:
        return match.group(1).strip()
    for name in _FAMOUS_POEMS:
        if name in text:
            return name
    json_match = _JSON_TITLE.search(text)
    if json_match:
        return json_match.group(1).strip()
    return None


def _content_from_tool_json(text: str) -> tuple[str | None, str | None, str | None]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None, None, None
    if not isinstance(data, dict):
        return None, None, None

    title: str | None = None
    author: str | None = None
    content: str | None = None

    if data.get("found") and isinstance(data.get("data"), dict):
        block = data["data"]
        title = block.get("title")
        author = block.get("author")
        content = block.get("original") or block.get("content")
    elif data.get("title"):
        title = data.get("title")
        content = data.get("original") or data.get("content")
        author = data.get("author")

    if title:
        return str(title).strip(), (str(author).strip() if author else None), (
            str(content).strip() if content else None
        )
    return None, None, None


def resolve_poem_context(
    messages: list[BaseMessage],
    query: str,
) -> dict[str, str]:
    """
    从对话历史解析诗题/作者/原文片段。
    仅在指代性提问（needs_poem_context）时生效。
    """
    if not needs_poem_context(query):
        return {}

    resolved: dict[str, str] = {}
    prior = messages[:-1] if messages else []

    for msg in reversed(prior):
        if isinstance(msg, ToolMessage):
            title, author, content = _content_from_tool_json(_message_text(msg))
            if title:
                resolved.setdefault("title", title)
                if author:
                    resolved.setdefault("author", author)
                if content:
                    resolved.setdefault("content", content)
                return resolved

    for msg in reversed(prior):
        text = _message_text(msg)
        title = _title_from_text(text)
        if title:
            resolved["title"] = title
            if isinstance(msg, AIMessage):
                for line in text.splitlines():
                    line = line.strip()
                    if re.search(r"[\u4e00-\u9fff]，", line) and len(line) <= 30:
                        resolved.setdefault("content", line)
                        break
            return resolved

    return resolved


def format_poem_context_hint(resolved: dict[str, str]) -> str:
    """将解析结果格式化为注入 LLM 的提示。"""
    if not resolved:
        return ""
    lines = ["## 对话中的诗词上下文（已从历史解析，勿再向用户索要诗题）"]
    if resolved.get("title"):
        lines.append(f"- 诗题：《{resolved['title']}》")
    if resolved.get("author"):
        lines.append(f"- 作者：{resolved['author']}")
    if resolved.get("content"):
        snippet = resolved["content"][:300]
        lines.append(f"- 原文片段：{snippet}")
    lines.append(
        "用户正在指代上述诗词。请以此诗题调用 poem_lookup / meter_analysis，"
        "不要回复「未提供诗题」。"
    )
    return "\n".join(lines)


def augment_query_with_context(query: str, resolved: dict[str, Any]) -> str:
    """将指代问句改写为带书名号诗题的明确表述（便于检索与工具参数）。"""
    title = resolved.get("title")
    if not title or not needs_poem_context(query):
        return query
    if _POEM_TITLE.search(query):
        return query
    return _ANAPHORA.sub(f"《{title}》", query, count=1)

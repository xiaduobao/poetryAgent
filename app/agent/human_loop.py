"""Human-in-the-loop：工具调用前等待用户确认。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Literal

from langchain_core.messages import messages_from_dict, messages_to_dict

from app.config import get_settings

logger = logging.getLogger(__name__)

HitlAction = Literal["approve", "reject"]
HITL_TRIGGER = "human_loop"

TOOL_DISPLAY: dict[str, str] = {
    "author_query": "作者查询",
    "meter_analysis": "格律分析",
    "style_compare": "风格对比",
    "poem_lookup": "诗词检索",
    "theme_recommend": "主题推荐",
    "allusion_explain": "典故释义",
    "writing_assistant": "创作辅助",
}

_PENDING_TTL_SEC = 3600
_pending: dict[str, dict[str, Any]] = {}


def message_requests_hitl(text: str) -> bool:
    """用户消息是否包含 human_loop 触发词。"""
    return HITL_TRIGGER in text.lower()


def strip_hitl_trigger(text: str) -> str:
    """移除触发词，保留实际问题内容。"""
    cleaned = re.sub(rf"(?i)\b{re.escape(HITL_TRIGGER)}\b", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def should_defer_hitl(message: str) -> bool:
    """全局开关开启且消息含 human_loop 时才走 HITL。"""
    if not get_settings().human_in_loop_enabled:
        return False
    return message_requests_hitl(message)


def prepare_agent_message(message: str) -> tuple[str, bool]:
    """返回 (去掉触发词后的消息, 是否请求 HITL)。"""
    hitl = should_defer_hitl(message)
    if not message_requests_hitl(message):
        return message, False
    stripped = strip_hitl_trigger(message)
    return (stripped or message), hitl


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, v in _pending.items() if now - v.get("_ts", 0) > _PENDING_TTL_SEC]
    for k in expired:
        _pending.pop(k, None)


def format_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in tool_calls:
        name = tc.get("name") if isinstance(tc, dict) else tc.name
        args = tc.get("args") if isinstance(tc, dict) else tc.args
        tool_call_id = tc.get("id") if isinstance(tc, dict) else tc.id
        if not isinstance(args, dict):
            args = {}
        out.append(
            {
                "id": tool_call_id,
                "name": name,
                "args": args,
                "label": TOOL_DISPLAY.get(name, name),
                "summary": _summarize_tool_call(name, args),
            }
        )
    return out


def _summarize_tool_call(name: str, args: dict[str, Any]) -> str:
    if name == "author_query":
        return f"查询作者：{args.get('name', '')}"
    if name == "meter_analysis":
        return f"分析格律：{args.get('title', '')}"
    if name == "style_compare":
        return f"对比：{args.get('author_a', '')} vs {args.get('author_b', '')}"
    if name == "poem_lookup":
        parts = [p for p in (args.get("title"), args.get("author")) if p]
        return f"检索诗词：{' / '.join(parts) or '—'}"
    if name == "theme_recommend":
        return f"主题推荐：{args.get('theme', '')}"
    if name == "allusion_explain":
        return f"典故释义：{args.get('query', '')}"
    if name == "writing_assistant":
        return f"创作辅助：{args.get('writing_type', '')} · {args.get('theme', '')}"
    return json.dumps(args, ensure_ascii=False)[:120]


def serialize_prepared(prepared: dict[str, Any], *, user_message: str) -> dict[str, Any]:
    state = dict(prepared["state"])
    state["messages"] = messages_to_dict(state.get("messages", []))
    return {
        "state": state,
        "intent": prepared["intent"],
        "mode": prepared["mode"],
        "token_usage": prepared.get("token_usage"),
        "sub_intents": prepared.get("sub_intents"),
        "is_compound": prepared.get("is_compound"),
        "user_message": user_message,
    }


def deserialize_prepared(data: dict[str, Any]) -> dict[str, Any]:
    state = dict(data["state"])
    state["messages"] = messages_from_dict(state.get("messages", []))
    prepared: dict[str, Any] = {
        "state": state,
        "intent": data["intent"],
        "mode": data["mode"],
    }
    if data.get("token_usage") is not None:
        prepared["token_usage"] = data["token_usage"]
    if data.get("sub_intents") is not None:
        prepared["sub_intents"] = data["sub_intents"]
    if data.get("is_compound") is not None:
        prepared["is_compound"] = data["is_compound"]
    return prepared


def save_pending(
    thread_id: str,
    prepared: dict[str, Any],
    *,
    user_message: str,
    tool_calls: list[dict[str, Any]],
) -> None:
    _purge_expired()
    _pending[thread_id] = {
        "_ts": time.time(),
        "prepared": serialize_prepared(prepared, user_message=user_message),
        "tool_calls": tool_calls,
    }
    logger.info("HITL pending saved for thread=%s tools=%s", thread_id, len(tool_calls))


def get_pending(thread_id: str) -> dict[str, Any] | None:
    _purge_expired()
    return _pending.get(thread_id)


def pop_pending(thread_id: str) -> dict[str, Any] | None:
    _purge_expired()
    return _pending.pop(thread_id, None)


def clear_pending(thread_id: str) -> None:
    _pending.pop(thread_id, None)


def build_interrupt_payload(
    thread_id: str,
    prepared: dict[str, Any],
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": "tool_approval",
        "thread_id": thread_id,
        "session_id": thread_id,
        "intent": prepared.get("intent", ""),
        "tool_calls": tool_calls,
        "message": "Agent 请求调用以下工具，请确认是否执行。",
    }

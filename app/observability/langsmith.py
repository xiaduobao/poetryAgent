"""LangSmith 追踪初始化与辅助工具。"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from app.config import Settings

_trace_session_id: ContextVar[str | None] = ContextVar("trace_session_id", default=None)


def init_langsmith(settings: Settings) -> None:
    """启动时写入 LangChain 追踪环境变量。"""
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        os.environ.pop("LANGCHAIN_TRACING_V2", None)
        return
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project


def trace_metadata(
    *,
    session_id: str | None = None,
    intent: str | None = None,
    mode: str | None = None,
    filters: dict | None = None,
    stream: bool | None = None,
    endpoint: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """统一 metadata 字段，供 Run 与 LLM config 复用。"""
    meta: dict[str, Any] = {}
    if session_id:
        meta["session_id"] = session_id
    if intent:
        meta["intent"] = intent
    if mode:
        meta["mode"] = mode
    if filters:
        meta["filters"] = filters
    if stream is not None:
        meta["stream"] = stream
    if endpoint:
        meta["endpoint"] = endpoint
    meta.update({k: v for k, v in extra.items() if v is not None})
    return meta


def get_run_config(**extra_metadata: Any) -> dict[str, Any]:
    """返回 LangChain invoke/astream 所需的 config。"""
    session_id = _trace_session_id.get()
    metadata = trace_metadata(session_id=session_id, **extra_metadata)
    config: dict[str, Any] = {"metadata": metadata}
    if session_id:
        config["tags"] = [f"session_id:{session_id}"]
    return config


@contextmanager
def trace_session(session_id: str) -> Iterator[None]:
    """在请求上下文中绑定 session_id，供子 Span 与 LLM config 使用。"""
    token = _trace_session_id.set(session_id)
    add_run_tag(f"session_id:{session_id}")
    try:
        yield
    finally:
        _trace_session_id.reset(token)


def update_run_metadata(**kwargs: Any) -> None:
    """向当前 Run 追加 metadata。"""
    run = get_current_run_tree()
    if run is None:
        return
    run.metadata.update({k: v for k, v in kwargs.items() if v is not None})


def add_run_tag(tag: str) -> None:
    """向当前 Run 追加 tag。"""
    run = get_current_run_tree()
    if run is None:
        return
    tags = list(run.tags or [])
    if tag not in tags:
        tags.append(tag)
    run.tags = tags


def truncate_input(text: str, limit: int = 500) -> str:
    """截断输入用于 trace inputs。"""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


__all__ = [
    "init_langsmith",
    "trace_metadata",
    "get_run_config",
    "trace_session",
    "update_run_metadata",
    "add_run_tag",
    "truncate_input",
    "traceable",
]

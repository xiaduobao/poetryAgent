"""从 LangChain 响应提取 Token 用量并写入 Prometheus。"""
from __future__ import annotations

from langchain_core.messages import BaseMessage

from app.observability.metrics import LLM_TOKENS


def usage_from_message(message: BaseMessage | object) -> int:
    meta = getattr(message, "usage_metadata", None) or {}
    if not isinstance(meta, dict):
        return 0
    total = meta.get("total_tokens")
    if total is not None:
        return int(total)
    inp = int(meta.get("input_tokens") or 0)
    out = int(meta.get("output_tokens") or 0)
    return inp + out


def record_llm_tokens(action: str, tokens: int) -> None:
    if tokens > 0:
        LLM_TOKENS.labels(action=action).inc(tokens)

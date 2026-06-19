"""Agent 路由决策日志：意图识别与执行链路可观测。"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).replace("\n", " ").strip()
    if len(text) > 120:
        return text[:120] + "…"
    return text


def log_route(event: str, **fields: Any) -> None:
    """输出统一格式的路由日志，便于 grep `[agent-route]`。"""
    parts = [f"{key}={_fmt(val)}" for key, val in fields.items() if val is not None and val != ""]
    detail = " | ".join(parts)
    if detail:
        logger.info("[agent-route] %s | %s", event, detail)
    else:
        logger.info("[agent-route] %s", event)

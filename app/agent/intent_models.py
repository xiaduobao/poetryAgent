"""意图识别与复合问题拆解的数据模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

INTENT_LITERAL = Literal[
    "rag",
    "tool_author",
    "tool_meter",
    "tool_compare",
    "tool_lookup",
    "tool_theme",
    "tool_allusion",
    "tool_writing",
    "chat",
]

VALID_INTENTS: tuple[str, ...] = (
    "rag",
    "tool_author",
    "tool_meter",
    "tool_compare",
    "tool_lookup",
    "tool_theme",
    "tool_allusion",
    "tool_writing",
    "chat",
)


class IntentResult(BaseModel):
    intent: INTENT_LITERAL
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class DecomposedSubQuery(BaseModel):
    text: str
    suggested_intent: INTENT_LITERAL = "chat"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class DecomposeResult(BaseModel):
    is_compound: bool
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    sub_queries: list[DecomposedSubQuery]


class SubQueryIntent(BaseModel):
    """运行时子任务（含分类与执行结果）。"""

    id: str
    text: str
    intent: str = "chat"
    intent_source: str = "rule"
    confidence: float = 0.0
    result: str = ""
    sources: list[dict] = Field(default_factory=list)

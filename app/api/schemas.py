"""API 请求/响应模型。"""
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    thread_id: str = Field(default="default", description="会话 ID，用于多轮记忆")
    author: str | None = Field(default=None, description="检索过滤：作者")
    dynasty: str | None = Field(default=None, description="检索过滤：朝代")
    genre: str | None = Field(default=None, description="检索过滤：体裁")


class ChatResponse(BaseModel):
    answer: str
    intent: str = ""
    thread_id: str = "default"
    rag_context_preview: str | None = None


class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1)
    author: str | None = None
    dynasty: str | None = None
    genre: str | None = None
    top_k: int = Field(default=4, ge=1, le=10)


class RAGResponse(BaseModel):
    query: str
    documents: list[dict[str, Any]]


class ToolAuthorRequest(BaseModel):
    name: str


class ToolMeterRequest(BaseModel):
    title: str
    content: str = ""


class ToolCompareRequest(BaseModel):
    author_a: str
    author_b: str

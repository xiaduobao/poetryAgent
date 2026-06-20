"""API 请求/响应模型。"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=2000)
    image_base64: str | None = Field(default=None, description="图片 base64（不含 data: 前缀）")
    thread_id: str = Field(default="default", description="会话 ID，用于多轮记忆")
    session_id: str | None = Field(default=None, description="会话 ID（与 thread_id 一致）")
    author: str | None = Field(default=None, description="检索过滤：作者")
    dynasty: str | None = Field(default=None, description="检索过滤：朝代")
    genre: str | None = Field(default=None, description="检索过滤：体裁")

    @model_validator(mode="after")
    def check_message_or_image(self) -> "ChatRequest":
        has_text = bool(self.message and self.message.strip())
        has_image = bool(self.image_base64 and self.image_base64.strip())
        if not has_text and not has_image:
            raise ValueError("须提供文字或图片")
        return self


class ChatResponse(BaseModel):
    answer: str
    intent: str = ""
    thread_id: str = "default"
    session_id: str | None = None
    rag_context_preview: str | None = None
    hitl: dict[str, Any] | None = Field(
        default=None,
        description="Human-in-the-loop 中断信息（需用户确认后继续）",
    )


class HitlResumeRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    action: Literal["approve", "reject"] = Field(
        ...,
        description="approve=执行工具；reject=跳过工具",
    )


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    intent: str | None = None
    sources: list[dict[str, Any]] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> "MessageOut":
        import json

        data: dict[str, Any] = {
            "id": obj.id,
            "role": obj.role,
            "content": obj.content,
            "intent": obj.intent,
            "created_at": obj.created_at,
            "sources": None,
        }
        raw = getattr(obj, "sources_json", None)
        if raw:
            try:
                data["sources"] = json.loads(raw)
            except json.JSONDecodeError:
                data["sources"] = None
        return cls(**data)


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionDetailOut(SessionOut):
    messages: list[MessageOut] = Field(default_factory=list)


class SessionCreateRequest(BaseModel):
    title: str = Field(default="新对话", max_length=200)


class SessionRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


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


class ToolPoemRequest(BaseModel):
    title: str = ""
    author: str = ""


class ToolThemeRequest(BaseModel):
    theme: str
    limit: int = Field(default=5, ge=1, le=10)


class ToolAllusionRequest(BaseModel):
    query: str


class ToolWritingRequest(BaseModel):
    writing_type: str
    theme: str = ""
    constraints: str = ""

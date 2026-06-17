"""LLM 工厂（OpenAI 兼容 API）。"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import get_settings


@lru_cache
def get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key or "sk-placeholder",
        base_url=settings.openai_api_base,
        temperature=0.3,
    )


@lru_cache
def get_vision_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.vision_model,
        api_key=settings.openai_api_key or "sk-placeholder",
        base_url=settings.openai_api_base,
        temperature=0.2,
    )

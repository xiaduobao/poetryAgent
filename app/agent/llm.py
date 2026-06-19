"""LLM 工厂（OpenAI 兼容 API）。"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings


def _dashscope_extra_body(settings: Settings) -> dict | None:
    """DashScope 非标准参数：qwen3.7-plus 等默认开启思考，需显式关闭以提速。"""
    model = settings.llm_model.lower()
    if not (model.startswith("qwen3") or "qwen3.7" in model):
        return None
    return {"enable_thinking": settings.llm_enable_thinking}


@lru_cache
def get_llm() -> ChatOpenAI:
    settings = get_settings()
    extra_body = _dashscope_extra_body(settings)
    kwargs: dict = {
        "model": settings.llm_model,
        "api_key": settings.openai_api_key or "sk-placeholder",
        "base_url": settings.openai_api_base,
        "temperature": 0.3,
    }
    if extra_body is not None:
        kwargs["extra_body"] = extra_body
    return ChatOpenAI(**kwargs)


@lru_cache
def get_vision_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.vision_model,
        api_key=settings.openai_api_key or "sk-placeholder",
        base_url=settings.openai_api_base,
        temperature=0.2,
    )

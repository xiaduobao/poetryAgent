"""LLM 工厂（OpenAI 兼容 API）。"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings


def _dashscope_extra_body(model: str, enable_thinking: bool) -> dict | None:
    """DashScope 非标准参数：qwen3.7-plus 等默认开启思考，需显式关闭以提速。"""
    model_lower = model.lower()
    if not (model_lower.startswith("qwen3") or "qwen3.7" in model_lower):
        return None
    return {"enable_thinking": enable_thinking}


def _build_chat_llm(
    *,
    model: str,
    enable_thinking: bool,
    temperature: float,
) -> ChatOpenAI:
    settings = get_settings()
    extra_body = _dashscope_extra_body(model, enable_thinking)
    kwargs: dict = {
        "model": model,
        "api_key": settings.openai_api_key or "sk-placeholder",
        "base_url": settings.openai_api_base,
        "temperature": temperature,
    }
    if extra_body is not None:
        kwargs["extra_body"] = extra_body
    return ChatOpenAI(**kwargs)


@lru_cache
def get_llm() -> ChatOpenAI:
    settings = get_settings()
    return _build_chat_llm(
        model=settings.llm_model,
        enable_thinking=settings.llm_enable_thinking,
        temperature=0.3,
    )


@lru_cache
def get_react_llm() -> ChatOpenAI:
    """ReAct 工具选择与多轮调用；默认 qwen-turbo，比主模型更快。"""
    settings = get_settings()
    model = (settings.react_llm_model or settings.llm_model).strip()
    return _build_chat_llm(
        model=model,
        enable_thinking=settings.llm_enable_thinking,
        temperature=0.2,
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

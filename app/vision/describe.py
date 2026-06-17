"""图片校验与视觉描述（供看图作诗）。"""
from __future__ import annotations

import base64
import binascii
import imghdr
from typing import Tuple

from langchain_core.messages import HumanMessage

from app.agent.llm import get_vision_llm
from app.observability.langsmith import get_run_config
from app.vision.prompts import VISION_DESCRIBE_PROMPT

MAX_IMAGE_BYTES = 4 * 1024 * 1024  # 4MB

_MIME_MAP = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def validate_image_base64(data: str) -> Tuple[bytes, str]:
    """校验 base64 图片，返回 (bytes, mime_type)。失败抛 ValueError。"""
    raw = (data or "").strip()
    if not raw:
        raise ValueError("图片数据为空")

    # 兼容 data URL 前缀
    if raw.startswith("data:"):
        header, _, payload = raw.partition(",")
        if not payload:
            raise ValueError("图片 data URL 格式无效")
        mime = header[5:].split(";")[0].strip().lower()
        if mime not in _MIME_MAP.values():
            raise ValueError("仅支持 JPEG、PNG、WebP 格式")
        try:
            image_bytes = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError("图片 base64 解码失败") from e
    else:
        try:
            image_bytes = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError("图片 base64 解码失败") from e
        kind = imghdr.what(None, h=image_bytes)
        if kind not in _MIME_MAP:
            raise ValueError("仅支持 JPEG、PNG、WebP 格式")
        mime = _MIME_MAP[kind]

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(f"图片大小不能超过 {MAX_IMAGE_BYTES // (1024 * 1024)}MB")

    return image_bytes, mime


def describe_image_for_poetry(image_bytes: bytes, mime: str) -> str:
    """调用视觉模型，生成供诗词创作使用的画面描述。"""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    llm = get_vision_llm()
    resp = llm.invoke(
        [
            HumanMessage(
                content=[
                    {"type": "text", "text": VISION_DESCRIBE_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ]
            )
        ],
        config=get_run_config(step="vision_describe"),
    )
    text = resp.content.strip() if hasattr(resp, "content") else str(resp).strip()
    if not text:
        raise RuntimeError("视觉模型未返回画面描述")
    return text


def build_image_writing_message(vision_output: str, user_request: str) -> str:
    """合成注入 Agent 的增强消息。"""
    from app.vision.prompts import DEFAULT_IMAGE_WRITING_REQUEST, IMAGE_WRITING_PREFIX

    request = (user_request or "").strip() or DEFAULT_IMAGE_WRITING_REQUEST
    return (
        f"{IMAGE_WRITING_PREFIX}\n"
        f"画面描述：{vision_output}\n"
        f"用户要求：{request}"
    )

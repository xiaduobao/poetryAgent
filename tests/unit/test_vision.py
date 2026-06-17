"""视觉模块单元测试。"""
from __future__ import annotations

import base64

import pytest

from app.vision.describe import build_image_writing_message, validate_image_base64

# 1x1 PNG
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_validate_image_base64_accepts_png():
    b64 = base64.b64encode(_TINY_PNG).decode("ascii")
    data, mime = validate_image_base64(b64)
    assert data == _TINY_PNG
    assert mime == "image/png"


def test_validate_image_base64_rejects_empty():
    with pytest.raises(ValueError, match="为空"):
        validate_image_base64("")


def test_validate_image_base64_rejects_invalid():
    with pytest.raises(ValueError):
        validate_image_base64("not-valid-base64!!!")


def test_build_image_writing_message_uses_default_request():
    msg = build_image_writing_message("远山含黛", "")
    assert msg.startswith("【看图创作】")
    assert "画面描述：远山含黛" in msg
    assert "用户要求：请根据画面意境写一首五言绝句" in msg


def test_build_image_writing_message_with_user_request():
    msg = build_image_writing_message("孤舟江上", "写一首七言绝句")
    assert "用户要求：写一首七言绝句" in msg

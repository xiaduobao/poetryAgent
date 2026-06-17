"""Token 用量提取测试。"""
from __future__ import annotations

from types import SimpleNamespace

from app.observability.tokens import usage_from_message


def test_usage_from_message_total_tokens():
    msg = SimpleNamespace(usage_metadata={"total_tokens": 128})
    assert usage_from_message(msg) == 128


def test_usage_from_message_input_output():
    msg = SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 20})
    assert usage_from_message(msg) == 30


def test_usage_from_message_missing():
    msg = SimpleNamespace(usage_metadata=None)
    assert usage_from_message(msg) == 0

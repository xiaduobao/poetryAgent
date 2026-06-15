"""输入安全过滤与内容审核。"""
from __future__ import annotations

import json
import logging
import re
from typing import Tuple

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

SENSITIVE_WORDS = frozenset(
    {"违禁词示例", "暴力煽动", "政治敏感示例"}
)

MAX_INPUT_LENGTH = 2000

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"忽略(以上|先前|之前)(的)?(所有)?指令"),
    re.compile(r"system\s*:\s*", re.I),
]


def _check_injection(text: str) -> str | None:
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return "输入包含可疑指令，请修改后重试"
    return None


async def _aliyun_moderate(text: str) -> str | None:
    settings = get_settings()
    if not settings.content_moderation_enabled:
        return None
    if not settings.aliyun_access_key_id or not settings.aliyun_access_key_secret:
        logger.warning("content moderation enabled but aliyun keys missing")
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"https://green.{settings.aliyun_region}.aliyuncs.com/",
                headers={"Content-Type": "application/json"},
                content=json.dumps(
                    {
                        "Service": "comment_detection",
                        "ServiceParameters": json.dumps({"content": text[:600]}),
                    }
                ),
            )
            if resp.status_code != 200:
                logger.warning("aliyun moderation http %s", resp.status_code)
                return None
            data = resp.json()
            if data.get("Code") != 200:
                return None
            labels = data.get("Data", {}).get("labels", "")
            if labels and labels != "normal":
                return "输入包含不当内容，请修改后重试"
    except Exception as e:
        logger.warning("aliyun moderation failed: %s", e)
    return None


def wrap_user_input(text: str) -> str:
    """用分隔符包裹用户输入，降低 Prompt Injection 风险。"""
    return f"<user_input>\n{text}\n</user_input>"


def sanitize_input(text: str) -> Tuple[str, str | None]:
    """
    校验并清洗用户输入。
    返回 (清洗后文本, 错误信息)；无错误时错误为 None。
    """
    if not text or not text.strip():
        return "", "输入不能为空"

    text = text.strip()
    if len(text) > MAX_INPUT_LENGTH:
        return "", f"输入过长，请控制在 {MAX_INPUT_LENGTH} 字以内"

    injection_err = _check_injection(text)
    if injection_err:
        return "", injection_err

    lowered = text.lower()
    for word in SENSITIVE_WORDS:
        if word in lowered or word in text:
            return "", "输入包含不当内容，请修改后重试"

    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text, None


async def sanitize_input_async(text: str) -> Tuple[str, str | None]:
    text, err = sanitize_input(text)
    if err:
        return text, err
    mod_err = await _aliyun_moderate(text)
    if mod_err:
        return "", mod_err
    return text, None

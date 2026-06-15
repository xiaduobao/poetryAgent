"""输入安全过滤。"""
import re
from typing import Tuple

# 简单敏感词表（演示用，生产可接外部词库）
SENSITIVE_WORDS = frozenset(
    {"违禁词示例", "暴力煽动", "政治敏感示例"}
)

MAX_INPUT_LENGTH = 2000


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

    lowered = text.lower()
    for word in SENSITIVE_WORDS:
        if word in lowered or word in text:
            return "", "输入包含不当内容，请修改后重试"

    # 去除控制字符
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text, None

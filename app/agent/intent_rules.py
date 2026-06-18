"""基于优先级的意图规则引擎。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from app.security.filter import strip_user_input

RuleFn = Callable[[str], bool]


@dataclass(frozen=True)
class IntentRule:
    name: str
    intent: str
    priority: int
    match: RuleFn
    confidence: float = 1.0


@dataclass(frozen=True)
class RuleMatch:
    intent: str
    priority: int
    confidence: float
    rule_name: str


_POEM_TITLE = re.compile(r"《.+?》")
_FAMOUS_POEMS = ("静夜思", "登高", "念奴娇", "赤壁")
_AUTHOR_HINT = re.compile(r"(诗人|作者|作家|词人)")
_NAME_BEFORE_DE = re.compile(r"[\u4e00-\u9fff]{2,4}的(生平|代表作|风格|诗歌)")


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def _build_rules() -> tuple[IntentRule, ...]:
    return (
        IntentRule(
            "image_writing",
            "tool_writing",
            100,
            lambda t: t.startswith("【看图创作】"),
        ),
        IntentRule(
            "writing",
            "tool_writing",
            95,
            lambda t: _has_any(t, ("写一首", "创作", "对联", "藏头", "填词", "仿写", "帮我写")),
        ),
        IntentRule(
            "allusion",
            "tool_allusion",
            90,
            lambda t: _has_any(t, ("什么意思", "指什么", "典故", "含义", "是指"))
            and _has_any(t, ("中的", "里的", "「", "『", "这句", "字")),
        ),
        IntentRule(
            "theme",
            "tool_theme",
            85,
            lambda t: _has_any(t, ("推荐", "有哪些", "关于"))
            and _has_any(
                t,
                ("诗", "词", "主题", "思乡", "送别", "怀古", "春天", "秋天", "爱情"),
            ),
        ),
        IntentRule(
            "lookup",
            "tool_lookup",
            80,
            lambda t: _has_any(t, ("查找", "原文", "注释", "译文", "全文", "哪首诗"))
            or (
                "《" in t
                and "》" in t
                and _has_any(t, ("原文", "注释", "译文", "查找", "全文"))
            ),
        ),
        IntentRule(
            "compare",
            "tool_compare",
            78,
            lambda t: _has_any(t, ("对比", "区别", "vs", "比较", "和"))
            and (
                _has_any(t, ("李白", "杜甫", "苏轼", "李清照", "诗人", "风格"))
                or _NAME_BEFORE_DE.search(t) is not None
            ),
        ),
        IntentRule(
            "author",
            "tool_author",
            75,
            lambda t: _has_any(t, ("生平", "介绍", "是谁", "代表作"))
            and (
                _AUTHOR_HINT.search(t) is not None
                or _NAME_BEFORE_DE.search(t) is not None
                or _has_any(t, ("李白", "杜甫", "苏轼", "李清照"))
            )
            and not _has_any(t, ("对比", "区别", "比较")),
        ),
        IntentRule(
            "meter",
            "tool_meter",
            70,
            lambda t: _has_any(t, ("格律", "平仄", "押韵", "体裁"))
            and not _has_any(t, ("赏析", "鉴赏")),
        ),
        IntentRule(
            "meter_analyze",
            "tool_meter",
            68,
            lambda t: "分析" in t
            and _has_any(t, ("格律", "平仄", "押韵"))
            and not _has_any(t, ("赏析", "鉴赏")),
        ),
        IntentRule(
            "appreciation",
            "rag",
            60,
            lambda t: _has_any(t, ("赏析", "鉴赏", "欣赏", "主旨"))
            or ("含义" in t and "《" in t),
        ),
        IntentRule(
            "poem_title",
            "rag",
            55,
            lambda t: (
                _POEM_TITLE.search(t) is not None
                or _has_any(t, _FAMOUS_POEMS)
            )
            and not _has_any(t, ("原文", "注释", "查找", "全文", "译文")),
        ),
    )


_RULES = _build_rules()


def match_intent_rules(text: str) -> list[RuleMatch]:
    """返回所有命中规则，按 priority 降序。"""
    clean = strip_user_input(text)
    matches: list[RuleMatch] = []
    for rule in _RULES:
        try:
            if rule.match(clean):
                matches.append(
                    RuleMatch(
                        intent=rule.intent,
                        priority=rule.priority,
                        confidence=rule.confidence,
                        rule_name=rule.name,
                    )
                )
        except Exception:
            continue
    matches.sort(key=lambda m: (-m.priority, -m.confidence))
    return matches


def rule_based_intent(text: str) -> str:
    """返回最高优先级规则意图；无命中则 chat。"""
    matches = match_intent_rules(text)
    if matches:
        return matches[0].intent
    return "chat"

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
_WRITING_EXCLUDE = (
    "创作背景",
    "写作背景",
    "历史背景",
    "创作年代",
    "创作过程",
    "创作意图",
    "什么背景",
    "写于什么",
    "作于什么",
)
_POEM_BACKGROUND_PHRASES = (
    "创作背景",
    "写作背景",
    "历史背景",
    "创作年代",
    "创作过程",
    "创作意图",
)
_POEM_BACKGROUND_QUERY = ("什么背景", "写于什么", "作于什么", "写于何时", "何时所作", "什么时候写")
_POEM_CONTEXT_HINTS = ("这首诗", "这首", "此词", "此曲", "这篇")


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def _has_poem_context(text: str) -> bool:
    return (
        _POEM_TITLE.search(text) is not None
        or _has_any(text, _POEM_CONTEXT_HINTS)
        or _has_any(text, _FAMOUS_POEMS)
        or _AUTHOR_HINT.search(text) is not None
    )


def _is_poem_background_query(text: str) -> bool:
    if _has_any(text, _POEM_BACKGROUND_PHRASES):
        return True
    return _has_any(text, _POEM_BACKGROUND_QUERY) and _has_poem_context(text)


def _is_writing_request(text: str) -> bool:
    return _has_any(
        text, ("写一首", "创作", "对联", "藏头", "填词", "仿写", "帮我写")
    ) and not _has_any(text, _WRITING_EXCLUDE)


def _build_rules() -> tuple[IntentRule, ...]:
    return (
        IntentRule(
            "image_writing",
            "tool_writing",
            100,
            lambda t: t.startswith("【看图创作】"),
            confidence=1.0,
        ),
        IntentRule(
            "poem_background",
            "rag",
            96,
            _is_poem_background_query,
            confidence=0.92,
        ),
        IntentRule(
            "writing",
            "tool_writing",
            95,
            _is_writing_request,
            confidence=0.95,
        ),
        IntentRule(
            "allusion",
            "tool_allusion",
            90,
            lambda t: _has_any(t, ("什么意思", "指什么", "典故", "含义", "是指"))
            and _has_any(t, ("中的", "里的", "「", "『", "这句", "字")),
            confidence=0.88,
        ),
        IntentRule(
            "theme",
            "tool_theme",
            85,
            lambda t: _has_any(t, ("推荐", "有哪些", "关于"))
            and _has_any(
                t,
                ("诗", "词", "主题", "思乡", "送别", "怀古", "春天", "秋天", "爱情"),
            )
            and not _has_any(t, ("作品", "代表作", "名篇", "诗篇", "诗作", "名诗")),
            confidence=0.88,
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
            confidence=0.95,
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
            confidence=0.92,
        ),
        IntentRule(
            "author_works",
            "tool_author",
            76,
            lambda t: _has_any(t, ("推荐", "有哪些", "列出", "列举", "介绍"))
            and _has_any(t, ("作品", "代表作", "名篇", "诗篇", "诗作", "名诗", "诗词"))
            and not _has_any(t, ("对比", "区别", "比较")),
            confidence=0.90,
        ),
        IntentRule(
            "author",
            "tool_author",
            75,
            lambda t: _has_any(
                t,
                ("生平", "介绍", "是谁", "代表作", "主要作品", "名篇"),
            )
            and (
                _AUTHOR_HINT.search(t) is not None
                or _NAME_BEFORE_DE.search(t) is not None
                or _has_any(t, ("李白", "杜甫", "苏轼", "李清照"))
            )
            and not _has_any(t, ("对比", "区别", "比较")),
            confidence=0.88,
        ),
        IntentRule(
            "meter",
            "tool_meter",
            70,
            lambda t: _has_any(t, ("格律", "平仄", "押韵", "体裁"))
            and not _has_any(t, ("赏析", "鉴赏")),
            confidence=0.92,
        ),
        IntentRule(
            "meter_analyze",
            "tool_meter",
            68,
            lambda t: "分析" in t
            and _has_any(t, ("格律", "平仄", "押韵"))
            and not _has_any(t, ("赏析", "鉴赏")),
            confidence=0.90,
        ),
        IntentRule(
            "appreciation",
            "rag",
            60,
            lambda t: _has_any(t, ("赏析", "鉴赏", "欣赏", "主旨"))
            or ("含义" in t and "《" in t),
            confidence=0.90,
        ),
        IntentRule(
            "poem_title",
            "rag",
            55,
            lambda t: (
                _POEM_TITLE.search(t) is not None
                or _has_any(t, _FAMOUS_POEMS)
            )
            and not _has_any(
                t,
                ("原文", "注释", "查找", "全文", "译文", "格律", "平仄", "押韵"),
            ),
            confidence=0.75,
        ),
    )


_RULES = _build_rules()

# 不同 intent 的 top 规则 priority 差 ≤ 此值时视为冲突，下调 confidence 触发 ReAct
RULE_AMBIGUITY_PRIORITY_GAP = 10
RULE_AMBIGUOUS_CONFIDENCE_CAP = 0.58


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


def is_ambiguous_rule_match(matches: list[RuleMatch]) -> bool:
    """多条不同 intent 的规则 priority 接近时视为冲突。"""
    if len(matches) < 2:
        return False
    best = matches[0]
    for other in matches[1:]:
        if other.intent == best.intent:
            continue
        if best.priority - other.priority <= RULE_AMBIGUITY_PRIORITY_GAP:
            return True
    return False


def resolve_rule_match(text: str) -> tuple[RuleMatch | None, bool]:
    """
    选取最佳规则命中；若存在 priority 接近的不同 intent，标记 ambiguous 并下调 confidence。
    """
    matches = match_intent_rules(text)
    if not matches:
        return None, False
    best = matches[0]
    ambiguous = is_ambiguous_rule_match(matches)
    if ambiguous:
        best = RuleMatch(
            intent=best.intent,
            priority=best.priority,
            confidence=min(best.confidence, RULE_AMBIGUOUS_CONFIDENCE_CAP),
            rule_name=best.rule_name,
        )
    return best, ambiguous


def rule_based_intent(text: str) -> str:
    """返回最高优先级规则意图；无命中则 chat。"""
    match, _ = resolve_rule_match(text)
    if match:
        return match.intent
    return "chat"

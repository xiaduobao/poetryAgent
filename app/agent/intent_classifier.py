"""意图分类：规则优先，上下文增强，多信号融合，LLM 结构化兜底。"""
from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import BaseMessage

from app.agent.context_resolver import augment_query_with_context, resolve_poem_context
from app.agent.intent_models import VALID_INTENTS, IntentResult
from app.agent.intent_rules import RuleMatch, resolve_rule_match
from app.agent.llm import get_llm
from app.agent.prompts import INTENT_CLASSIFIER_PROMPT
from app.agent.route_log import log_route
from app.observability.langsmith import get_run_config
from app.security.filter import strip_user_input

logger = logging.getLogger(__name__)

# decompose 建议意图可直接采用的下限（原 0.8，融合后略降以减少重复 LLM）
SUGGESTED_INTENT_MIN_CONF = 0.7
# rule 与 suggested 冲突时，suggested 需达到此值才可能覆盖 rule
SUGGESTED_OVERRIDE_MIN_CONF = 0.9


def prepare_query_for_intent(
    text: str,
    messages: list[BaseMessage] | None = None,
) -> tuple[str, str]:
    """
    分类前解析指代并改写问句（如「这首诗」→「《静夜思》」）。
    返回 (augmented_query, original_clean)。
    """
    clean = strip_user_input(text)
    if not messages:
        return clean, clean
    resolved = resolve_poem_context(messages, clean)
    augmented = augment_query_with_context(clean, resolved)
    return augmented, clean


def _parse_intent_json(raw: str) -> IntentResult | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        intent = data.get("intent", "chat")
        if intent not in VALID_INTENTS:
            intent = "chat"
        return IntentResult(
            intent=intent,  # type: ignore[arg-type]
            confidence=float(data.get("confidence", 0.7)),
            reasoning=str(data.get("reasoning", "")),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _parse_intent_fallback(raw: str) -> IntentResult:
    lowered = raw.strip().lower()
    for key in VALID_INTENTS:
        if key in lowered:
            return IntentResult(intent=key, confidence=0.6, reasoning="substring_match")
    return IntentResult(intent="chat", confidence=0.5, reasoning="default_chat")


def _llm_classify_intent(text: str) -> IntentResult:
    llm = get_llm()
    prompt = INTENT_CLASSIFIER_PROMPT.format(query=text)
    try:
        structured = llm.with_structured_output(IntentResult)
        result = structured.invoke(
            prompt,
            config=get_run_config(step="intent_classifier"),
        )
        if isinstance(result, IntentResult):
            return result
    except Exception as e:
        logger.debug("structured intent classify failed: %s", e)

    resp = llm.invoke(
        prompt,
        config=get_run_config(step="intent_classifier"),
    )
    raw = resp.content.strip() if hasattr(resp, "content") else str(resp)
    parsed = _parse_intent_json(raw)
    if parsed:
        return parsed
    return _parse_intent_fallback(raw)


def _valid_suggested(
    suggested_intent: str | None,
    suggested_confidence: float,
    *,
    min_conf: float = SUGGESTED_INTENT_MIN_CONF,
) -> bool:
    return bool(
        suggested_intent
        and suggested_intent in VALID_INTENTS
        and suggested_confidence >= min_conf
    )


def _fuse_rule_and_suggested(
    rule_match: RuleMatch | None,
    rule_ambiguous: bool,
    suggested_intent: str | None,
    suggested_confidence: float,
) -> tuple[str, str, float] | None:
    """
    融合规则与 decompose 建议；一致则提置信，冲突则降置信或采 suggested。
    返回 None 表示需走 LLM。
    """
    has_rule = rule_match is not None
    has_suggested = _valid_suggested(suggested_intent, suggested_confidence)

    if has_rule and has_suggested:
        assert rule_match is not None
        assert suggested_intent is not None
        if rule_match.intent == suggested_intent:
            conf = max(rule_match.confidence, suggested_confidence)
            if rule_ambiguous:
                conf = min(conf, 0.62)
            return rule_match.intent, "rule+suggested", conf

        if suggested_confidence >= SUGGESTED_OVERRIDE_MIN_CONF and rule_match.confidence < 0.8:
            return suggested_intent, "suggested", suggested_confidence * 0.92

        conf = rule_match.confidence
        if rule_ambiguous:
            conf = min(conf, 0.55)
        else:
            conf = min(conf, 0.62)
        return rule_match.intent, "rule", conf

    if has_rule:
        assert rule_match is not None
        return rule_match.intent, "rule", rule_match.confidence

    if has_suggested:
        assert suggested_intent is not None
        return suggested_intent, "suggested", suggested_confidence

    return None


def classify_single_intent(
    text: str,
    *,
    suggested_intent: str | None = None,
    suggested_confidence: float = 0.0,
    messages: list[BaseMessage] | None = None,
) -> tuple[str, str, float]:
    """
    对单条文本分类意图。
    返回 (intent, source, confidence)。
    """
    augmented, original = prepare_query_for_intent(text, messages)
    if not original.strip():
        log_route("intent_classify", source="empty", intent="chat", query=original)
        return "chat", "empty", 1.0

    rule_match, rule_ambiguous = resolve_rule_match(augmented)
    fused = _fuse_rule_and_suggested(
        rule_match,
        rule_ambiguous,
        suggested_intent,
        suggested_confidence,
    )
    if fused:
        intent, source, confidence = fused
        log_route(
            "intent_classify",
            source=source,
            intent=intent,
            confidence=confidence,
            rule=rule_match.rule_name if rule_match else None,
            ambiguous=rule_ambiguous,
            augmented=augmented != original,
            query=original,
        )
        return intent, source, confidence

    llm_result = _llm_classify_intent(augmented)
    log_route(
        "intent_classify",
        source="llm",
        intent=llm_result.intent,
        confidence=llm_result.confidence,
        reasoning=llm_result.reasoning,
        augmented=augmented != original,
        query=original,
    )
    return llm_result.intent, "llm", llm_result.confidence

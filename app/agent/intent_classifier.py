"""意图分类：规则优先，LLM 结构化兜底。"""
from __future__ import annotations

import json
import logging
import re

from app.agent.intent_models import INTENT_LITERAL, VALID_INTENTS, IntentResult
from app.agent.intent_rules import match_intent_rules, rule_based_intent
from app.agent.llm import get_llm
from app.agent.prompts import INTENT_CLASSIFIER_PROMPT
from app.observability.langsmith import get_run_config
from app.security.filter import strip_user_input

logger = logging.getLogger(__name__)


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


def classify_single_intent(
    text: str,
    *,
    suggested_intent: str | None = None,
    suggested_confidence: float = 0.0,
) -> tuple[str, str, float]:
    """
    对单条文本分类意图。
    返回 (intent, source, confidence)。
    """
    clean = strip_user_input(text)
    if not clean.strip():
        return "chat", "empty", 1.0

    matches = match_intent_rules(clean)
    if matches:
        best = matches[0]
        return best.intent, "rule", best.confidence

    if (
        suggested_intent
        and suggested_intent in VALID_INTENTS
        and suggested_confidence >= 0.8
    ):
        return suggested_intent, "suggested", suggested_confidence

    llm_result = _llm_classify_intent(clean)
    return llm_result.intent, "llm", llm_result.confidence

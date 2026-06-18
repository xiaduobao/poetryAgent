"""意图评测脚本 smoke test。"""
from __future__ import annotations

import json
from pathlib import Path

from app.eval.intent_eval import evaluate_rules, load_golden


def test_golden_set_loads():
    rows = load_golden()
    assert len(rows) >= 10


def test_evaluate_rules_runs():
    metrics = evaluate_rules(load_golden())
    assert metrics["total"] >= 10
    assert 0 <= metrics["rule_intent_accuracy"] <= 1


def test_golden_file_valid_json():
    path = Path(__file__).resolve().parents[1] / "eval" / "intent_golden_set.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for row in data:
        assert "input" in row
        assert "expected_sub_queries" in row

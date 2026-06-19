"""意图识别评测：规则 + 启发式拆解（不调用 LLM）。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.agent.compound_pipeline import _heuristic_decompose
from app.agent.intent_classifier import classify_single_intent
from app.agent.intent_rules import rule_based_intent

GOLDEN_PATH = Path(__file__).resolve().parents[2] / "tests" / "eval" / "intent_golden_set.json"


def load_golden(path: Path | None = None) -> list[dict]:
    p = path or GOLDEN_PATH
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def evaluate_rules(rows: list[dict] | None = None) -> dict:
    rows = rows if rows is not None else load_golden()
    total = len(rows)
    intent_hits = 0
    compound_hits = 0
    decompose_rows = 0

    for row in rows:
        text = row["input"]
        expected_intents = [sq["intent"] for sq in row["expected_sub_queries"]]
        primary_expected = expected_intents[0]

        predicted = rule_based_intent(text)
        if predicted == primary_expected:
            intent_hits += 1

        if row.get("is_compound"):
            decompose_rows += 1
            decomposed = _heuristic_decompose(text)
            if decomposed.is_compound == row["is_compound"]:
                compound_hits += 1
            pred_intents = [
                classify_single_intent(sq.text)[0] for sq in decomposed.sub_queries
            ]
            if len(pred_intents) == len(expected_intents):
                if all(p == e for p, e in zip(pred_intents, expected_intents)):
                    compound_hits += 1

    return {
        "total": total,
        "rule_intent_accuracy": round(intent_hits / total, 3) if total else 0,
        "compound_cases": decompose_rows,
        "compound_score": compound_hits,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Intent classification eval (rules)")
    parser.add_argument("--report", action="store_true", help="Print report")
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    args = parser.parse_args()

    rows = load_golden(args.golden)
    metrics = evaluate_rules(rows)
    if args.report or True:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

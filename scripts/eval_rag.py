#!/usr/bin/env python3
"""RAG 检索质量简易评估（离线，需已构建向量库）。

关键词 smoke test，不消耗 LLM API。全链路 Ragas 评估见 scripts/eval_rag_ragas.py。

用法:
    python scripts/eval_rag.py
    python scripts/eval_rag.py --golden tests/eval/rag_golden_set.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_GOLDEN = ROOT / "tests" / "eval" / "rag_golden_set.json"


def load_cases(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def evaluate_case(case: dict) -> tuple[bool, str]:
    from app.rag.retriever import get_hybrid_retriever

    query = case["query"]
    author = case.get("author")
    min_docs = int(case.get("min_docs", 1))
    expect_keywords = case.get("expect_keywords") or []

    retriever = get_hybrid_retriever()
    docs = retriever.retrieve(query, author=author)
    if len(docs) < min_docs:
        return False, f"召回 {len(docs)} 篇，低于 min_docs={min_docs}"

    combined = "\n".join(d.page_content for d in docs)
    for kw in expect_keywords:
        if kw not in combined:
            return False, f"未命中关键词: {kw}"

    return True, f"召回 {len(docs)} 篇"


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG golden set 评估")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    args = parser.parse_args()

    if not args.golden.is_file():
        print(f"golden set 不存在: {args.golden}", file=sys.stderr)
        return 1

    cases = load_cases(args.golden)
    passed = 0
    print(f"评估 {len(cases)} 条用例 ({args.golden.name})")
    print("-" * 50)

    for i, case in enumerate(cases, 1):
        try:
            ok, msg = evaluate_case(case)
        except Exception as e:
            ok, msg = False, f"异常: {e}"
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] #{i} query={case['query']!r} — {msg}")
        if ok:
            passed += 1

    print("-" * 50)
    print(f"结果: {passed}/{len(cases)} 通过")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())

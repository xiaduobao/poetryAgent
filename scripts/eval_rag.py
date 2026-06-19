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


def evaluate_case(case: dict) -> tuple[bool, str, int]:
    from app.rag.retriever import get_hybrid_retriever

    query = case["query"]
    author = case.get("author")
    min_docs = int(case.get("min_docs", 1))
    expect_keywords = case.get("expect_keywords") or []

    retriever = get_hybrid_retriever()
    docs = retriever.retrieve(query, author=author)
    doc_count = len(docs)
    if doc_count < min_docs:
        return False, f"召回 {doc_count} 篇，低于 min_docs={min_docs}", doc_count

    combined = "\n".join(d.page_content for d in docs)
    for kw in expect_keywords:
        if kw not in combined:
            return False, f"未命中关键词: {kw}", doc_count

    return True, f"召回 {doc_count} 篇", doc_count


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG golden set 评估")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--output", type=Path, help="将评估结果写入 JSON（含通过率、平均召回数）")
    args = parser.parse_args()

    if not args.golden.is_file():
        print(f"golden set 不存在: {args.golden}", file=sys.stderr)
        return 1

    cases = load_cases(args.golden)
    passed = 0
    doc_counts: list[int] = []
    results: list[dict] = []
    print(f"评估 {len(cases)} 条用例 ({args.golden.name})")
    print("-" * 50)

    for i, case in enumerate(cases, 1):
        try:
            ok, msg, doc_n = evaluate_case(case)
        except Exception as e:
            ok, msg, doc_n = False, f"异常: {e}", 0
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] #{i} query={case['query']!r} — {msg}")
        results.append({"query": case["query"], "pass": ok, "message": msg, "doc_count": doc_n})
        if ok:
            passed += 1
            doc_counts.append(doc_n)

    total = len(cases)
    pass_rate = passed / total if total else 0.0
    avg_docs = sum(doc_counts) / len(doc_counts) if doc_counts else 0.0

    print("-" * 50)
    print(f"结果: {passed}/{total} 通过 ({pass_rate:.0%})")
    if doc_counts:
        print(f"平均召回: {avg_docs:.2f} 篇/查询")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "golden_set": str(args.golden.relative_to(ROOT)),
            "total_cases": total,
            "passed": passed,
            "pass_rate": round(pass_rate, 4),
            "avg_doc_count": round(avg_docs, 2),
            "cases": results,
        }
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"报告已写入: {args.output}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

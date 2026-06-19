#!/usr/bin/env python3
"""使用 Ragas 评估诗词 RAG 全链路（检索 + 生成）。

需已构建向量库，且 .env 中配置 OPENAI_API_KEY（通义千问 DashScope）。

用法:
    python scripts/eval_rag_ragas.py
    python scripts/eval_rag_ragas.py --golden tests/eval/rag_golden_set.json
    python scripts/eval_rag_ragas.py --retrieval-only   # 仅评检索（ContextRecall）
    python scripts/eval_rag_ragas.py --output reports/ragas_result.json
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Ragas RAG 评估")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="仅评估检索质量（LLMContextRecall），不调用 LLM 生成回答",
    )
    parser.add_argument("--output", type=Path, help="将指标结果写入 JSON 文件")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="仅评估前 N 条用例（0 表示全部，用于快速试跑）",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default="",
        help="Ragas 评判用 LLM（默认读 LLM_MODEL；qwen-plus 免费额度耗尽时可试 qwen-turbo）",
    )
    args = parser.parse_args()

    if args.llm_model:
        import os

        os.environ["LLM_MODEL"] = args.llm_model

    if not args.golden.is_file():
        print(f"golden set 不存在: {args.golden}", file=sys.stderr)
        return 1

    from app.eval.ragas_runner import (
        build_evaluation_dataset,
        load_golden_cases,
        result_to_dict,
        result_to_rows,
        run_ragas_eval,
    )

    cases = load_golden_cases(args.golden)
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]
    if not cases:
        print("golden set 为空", file=sys.stderr)
        return 1

    print(f"加载 {len(cases)} 条用例 ({args.golden.name})")
    print("构建评估数据集（检索" + (" + 生成" if not args.retrieval_only else "") + "）…")

    rows = build_evaluation_dataset(
        cases,
        generate_answers=not args.retrieval_only,
    )

    for i, row in enumerate(rows, 1):
        ctx_n = len(row.get("retrieved_contexts") or [])
        print(f"  #{i} query={row['user_input']!r} — 召回 {ctx_n} 段上下文")

    print("运行 Ragas 指标（需 LLM API，可能耗时数分钟）…")
    try:
        result = run_ragas_eval(rows, retrieval_only=args.retrieval_only)
    except Exception as e:
        print(f"Ragas 评估失败: {e}", file=sys.stderr)
        return 1

    scores = result_to_dict(result)
    per_case = result_to_rows(result)
    print("-" * 50)
    print("Ragas 评估结果（均值）:")
    if scores:
        for name, value in sorted(scores.items()):
            print(f"  {name}: {value:.4f}")
    else:
        print("  （无数值分数，可能 API 配额不足或全部用例失败）")
    print("-" * 50)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        from datetime import date

        from app.config import get_settings

        settings = get_settings()
        payload = {
            "evaluated_at": date.today().isoformat(),
            "golden": str(args.golden),
            "retrieval_only": args.retrieval_only,
            "llm_model": settings.llm_model,
            "case_count": len(cases),
            "scores": scores,
            "per_case": per_case,
            "notes": (
                "retrieval_only 时仅含 context_recall；"
                "全链路含 faithfulness / answer_relevancy / factual_correctness。"
                "qwen-plus 免费额度耗尽时请加 --llm-model qwen-turbo"
            ),
        }
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"已写入 {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

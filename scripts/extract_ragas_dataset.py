#!/usr/bin/env python3
"""从 pg_dump SQL 导出文件中抽取生产对话，生成 Ragas 测评 golden set。

用法:
    python scripts/extract_ragas_dataset.py
    python scripts/extract_ragas_dataset.py --input backups/poetry_agent_20260622.sql
    python scripts/extract_ragas_dataset.py --tier high --output tests/eval/rag_production_golden_set.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

RAG_INTENTS = frozenset(
    {
        "rag",
        "tool_theme",
        "tool_author",
        "tool_lookup",
        "tool_allusion",
        "tool_compare",
        "tool_meter",
    }
)

FOLLOW_UP_PATTERNS = (
    r"^作者还",
    r"^再",
    r"^继续",
    r"^上面",
    r"^这首",
    r"^它",
    r"上传",
    r"看图",
    r"human_loop",
)

LOW_QUALITY_PATTERNS = (
    r"其中一首",
    r"这首诗",
    r"这位诗人",
    r"他的作品$",
    r"^推荐他的作品",
    r"和李白比",
    r"不够押韵",
    r"王加宝",
    r"王家宝",
    r"帮我赏析其中",
    r"相关主题",
    r"诗中有什么典故",
)

KNOWN_AUTHORS = (
    "李白",
    "杜甫",
    "苏轼",
    "白居易",
    "王维",
    "孟浩然",
    "辛弃疾",
    "李清照",
    "范仲淹",
    "王翰",
    "张继",
)


def parse_messages_sql(path: Path) -> list[dict[str, Any]]:
    """解析 pg_dump 中 messages 表的 COPY 数据块。"""
    rows: list[dict[str, Any]] = []
    in_messages = False
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("COPY public.messages"):
                in_messages = True
                continue
            if not in_messages:
                continue
            if line.strip() == r"\.":
                break
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 7:
                continue
            rows.append(
                {
                    "id": parts[0],
                    "session_id": parts[1],
                    "role": parts[2],
                    "content": parts[3],
                    "intent": None if parts[4] == r"\N" else parts[4],
                    "sources_json": None if parts[5] == r"\N" else parts[5],
                    "created_at": parts[6],
                }
            )
    return rows


def pair_user_assistant(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for msg in messages:
        by_session[msg["session_id"]].append(msg)

    pairs: list[dict[str, Any]] = []
    for session_id, msgs in by_session.items():
        msgs.sort(key=lambda m: m["created_at"])
        pending_user: dict[str, Any] | None = None
        for msg in msgs:
            if msg["role"] == "user":
                pending_user = msg
            elif msg["role"] == "assistant" and pending_user is not None:
                pairs.append(
                    {
                        "message_id": msg["id"],
                        "session_id": session_id,
                        "query": pending_user["content"].strip(),
                        "reference": msg["content"].strip(),
                        "intent": msg["intent"],
                        "sources_json": msg["sources_json"],
                        "created_at": msg["created_at"],
                    }
                )
                pending_user = None
    return pairs


def unescape_pg_text(text: str) -> str:
    return text.replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\")


def normalize_query(query: str) -> str:
    q = query.replace("\\n", " ").replace("\n", " ")
    q = re.sub(r"\s+", " ", q.strip())
    return q


def dedupe_key(query: str) -> str:
    """取首个问句片段，合并「风格区别 + 代表作品」等复合追问。"""
    q = normalize_query(query)
    head = re.split(r"[?？]", q, maxsplit=1)[0].strip()
    return re.sub(r"\s+", "", head.lower())


def is_standalone_query(query: str) -> bool:
    if len(query) < 4:
        return False
    for pattern in FOLLOW_UP_PATTERNS:
        if re.search(pattern, query):
            return False
    return True


def is_high_quality_query(query: str) -> bool:
    if not is_standalone_query(query):
        return False
    for pattern in LOW_QUALITY_PATTERNS:
        if re.search(pattern, query):
            return False
    return True


def extract_author(query: str) -> str | None:
    if re.search(r"《[^》]+》", query):
        return None
    for name in KNOWN_AUTHORS:
        if name in query:
            return name
    return None


def parse_sources(sources_json: str | None) -> list[dict[str, Any]] | None:
    if not sources_json:
        return None
    try:
        data = json.loads(sources_json)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def build_cases(
    pairs: list[dict[str, Any]],
    *,
    tier: str,
    min_response_len: int,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    cases: list[dict[str, Any]] = []

    for pair in pairs:
        if pair["intent"] not in RAG_INTENTS:
            continue

        query = normalize_query(pair["query"])
        if tier == "high" and not is_high_quality_query(query):
            continue
        if tier == "all" and not is_standalone_query(query):
            continue
        if len(pair["reference"]) < min_response_len:
            continue

        dedupe_key_val = dedupe_key(query)
        if dedupe_key_val in seen:
            continue
        seen.add(dedupe_key_val)

        case: dict[str, Any] = {
            "query": query,
            "reference": unescape_pg_text(pair["reference"]),
            "response": unescape_pg_text(pair["reference"]),
            "intent": pair["intent"],
            "source": "production",
            "message_id": pair["message_id"],
            "session_id": pair["session_id"],
        }
        author = extract_author(query)
        if author:
            case["author"] = author

        sources = parse_sources(pair["sources_json"])
        if sources:
            case["production_sources"] = sources

        cases.append(case)

    cases.sort(key=lambda c: (c["intent"], c["query"]))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="从生产 SQL 导出抽取 Ragas golden set")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "backups" / "poetry_agent_20260622.sql",
        help="pg_dump 生成的 .sql 文件",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tests" / "eval" / "rag_production_golden_set.json",
    )
    parser.add_argument(
        "--tier",
        choices=("high", "all"),
        default="high",
        help="high=独立、可复现问题；all=包含更多上下文依赖问法",
    )
    parser.add_argument("--min-response-len", type=int, default=80)
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"输入文件不存在: {args.input}", file=sys.stderr)
        return 1

    messages = parse_messages_sql(args.input)
    pairs = pair_user_assistant(messages)
    cases = build_cases(pairs, tier=args.tier, min_response_len=args.min_response_len)

    if not cases:
        print("未抽取到可用用例，请检查过滤条件或输入文件", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    from collections import Counter

    intent_counts = Counter(c["intent"] for c in cases)
    print(f"输入消息: {len(messages)} 条，问答对: {len(pairs)} 对")
    print(f"输出: {len(cases)} 条 ({args.tier}) -> {args.output}")
    for intent, count in intent_counts.most_common():
        print(f"  {intent}: {count}")
    print("\n运行 Ragas:")
    print(
        f"  python scripts/eval_rag_ragas.py --golden {args.output} "
        "--retrieval-only --llm-model qwen-turbo --output reports/ragas_production.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""查询 Chroma 向量库真实数据（documents / embeddings / metadatas）。

用法:
    python scripts/inspect_chroma.py --stats
    python scripts/inspect_chroma.py --limit 3
    python scripts/inspect_chroma.py --limit 10 --output reports/chroma_sample.json
    python scripts/inspect_chroma.py --id <chunk_id>
    python scripts/inspect_chroma.py --where '{"author":"杜甫"}'
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_INCLUDE = ["documents", "embeddings", "metadatas"]


def parse_include(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    allowed = {"documents", "embeddings", "metadatas", "uris", "data"}
    invalid = set(parts) - allowed
    if invalid:
        raise ValueError(f"不支持的 include 字段: {', '.join(sorted(invalid))}")
    return parts or list(DEFAULT_INCLUDE)


def get_client(persist_dir: Path):
    import chromadb

    return chromadb.PersistentClient(path=str(persist_dir))


def get_collection(client, name: str):
    collections = client.list_collections()
    names = [c.name for c in collections]
    if name not in names:
        raise SystemExit(
            f"collection '{name}' 不存在。可用: {', '.join(names) or '(空)'}"
        )
    return client.get_collection(name)


def fetch_records(
    collection,
    *,
    limit: int | None,
    offset: int,
    ids: list[str] | None,
    where: dict[str, Any] | None,
    include: list[str],
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"include": include}
    if ids:
        kwargs["ids"] = ids
    else:
        if limit is not None:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset
        if where:
            kwargs["where"] = where
    return collection.get(**kwargs)


def summarize(collection, include: list[str]) -> dict[str, Any]:
    total = collection.count()
    sample = collection.get(limit=1, include=include)
    meta_keys: set[str] = set()
    if sample.get("metadatas"):
        for meta in sample["metadatas"]:
            if meta:
                meta_keys.update(meta.keys())

    embedding_dim: int | None = None
    embeddings = sample.get("embeddings")
    if embeddings is not None and len(embeddings) > 0 and embeddings[0] is not None:
        embedding_dim = len(embeddings[0])

    return {
        "collection": collection.name,
        "count": total,
        "include": include,
        "embedding_dim": embedding_dim,
        "metadata_keys_sample": sorted(meta_keys),
    }


def format_record(
    record_id: str,
    payload: dict[str, Any],
    idx: int,
    *,
    doc_preview: int,
    embedding_preview: int,
) -> dict[str, Any]:
    item: dict[str, Any] = {"id": record_id}
    metas = payload.get("metadatas")
    docs = payload.get("documents")
    embs = payload.get("embeddings")
    if metas is None:
        metas = []
    if docs is None:
        docs = []
    if embs is None:
        embs = []

    if idx < len(metas) and metas[idx] is not None:
        item["metadata"] = metas[idx]
    if idx < len(docs) and docs[idx] is not None:
        doc = docs[idx]
        item["document"] = doc
        if doc_preview > 0 and len(doc) > doc_preview:
            item["document_preview"] = doc[:doc_preview] + "…"
    if idx < len(embs) and embs[idx] is not None:
        emb = list(embs[idx])
        item["embedding_dim"] = len(emb)
        if embedding_preview > 0:
            item["embedding_preview"] = emb[:embedding_preview]
        else:
            item["embedding"] = emb
    return item


def build_output_rows(
    payload: dict[str, Any],
    *,
    doc_preview: int,
    embedding_preview: int,
    full: bool,
) -> list[dict[str, Any]]:
    ids = payload.get("ids") or []
    rows: list[dict[str, Any]] = []
    for i, record_id in enumerate(ids):
        if full:
            row: dict[str, Any] = {"id": record_id}
            if payload.get("metadatas") and i < len(payload["metadatas"]):
                row["metadata"] = payload["metadatas"][i]
            if payload.get("documents") and i < len(payload["documents"]):
                row["document"] = payload["documents"][i]
            if payload.get("embeddings") and i < len(payload["embeddings"]):
                row["embedding"] = list(payload["embeddings"][i])
            rows.append(row)
        else:
            rows.append(
                format_record(
                    record_id,
                    payload,
                    i,
                    doc_preview=doc_preview,
                    embedding_preview=embedding_preview,
                )
            )
    return rows


def print_stats(collection, include: list[str]) -> None:
    info = summarize(collection, include)
    print(f"collection : {info['collection']}")
    print(f"count      : {info['count']}")
    print(f"include    : {info['include']}")
    print(f"emb_dim    : {info['embedding_dim']}")
    print(f"meta_keys  : {', '.join(info['metadata_keys_sample']) or '(无)'}")

    if info["count"] == 0:
        return

    payload = collection.get(include=["metadatas"])
    authors = Counter(
        (m or {}).get("author", "(unknown)") for m in (payload.get("metadatas") or [])
    )
    print("\n作者分布 Top 10:")
    for author, count in authors.most_common(10):
        print(f"  {author}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="查询 Chroma 向量库真实数据")
    parser.add_argument(
        "--persist-dir",
        type=Path,
        default=None,
        help="Chroma 持久化目录（默认读 CHROMA_PERSIST_DIR）",
    )
    parser.add_argument(
        "--collection",
        default="poetry_corpus",
        help="collection 名称（默认 poetry_corpus）",
    )
    parser.add_argument(
        "--include",
        default=",".join(DEFAULT_INCLUDE),
        help="get(include=...) 字段，逗号分隔",
    )
    parser.add_argument("--limit", type=int, default=5, help="最多返回条数（0=全部）")
    parser.add_argument("--offset", type=int, default=0, help="跳过前 N 条")
    parser.add_argument("--id", dest="ids", action="append", default=[], help="按 id 查询，可重复")
    parser.add_argument("--where", default="", help='metadata 过滤 JSON，如 \'{"author":"杜甫"}\'')
    parser.add_argument("--stats", action="store_true", help="仅打印库统计")
    parser.add_argument("--output", type=Path, help="写入 JSON 文件（含完整 embedding）")
    parser.add_argument(
        "--full",
        action="store_true",
        help="控制台也输出完整 document/embedding（默认只 preview）",
    )
    parser.add_argument("--doc-preview", type=int, default=200, help="document 预览字符数")
    parser.add_argument(
        "--embedding-preview",
        type=int,
        default=8,
        help="embedding 预览维度数（--full 或 --output 时忽略）",
    )
    args = parser.parse_args()

    try:
        include = parse_include(args.include)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    from app.config import get_settings

    settings = get_settings()
    persist_dir = args.persist_dir or Path(settings.chroma_persist_dir)
    if not persist_dir.is_dir():
        print(f"Chroma 目录不存在: {persist_dir}", file=sys.stderr)
        return 1

    where: dict[str, Any] | None = None
    if args.where:
        try:
            where = json.loads(args.where)
        except json.JSONDecodeError as e:
            print(f"--where JSON 无效: {e}", file=sys.stderr)
            return 1

    client = get_client(persist_dir)
    collection = get_collection(client, args.collection)

    if args.stats:
        print_stats(collection, include)
        return 0

    limit = None if args.limit == 0 else args.limit
    ids = args.ids or None
    payload = fetch_records(
        collection,
        limit=limit,
        offset=args.offset,
        ids=ids,
        where=where,
        include=include,
    )

    rows = build_output_rows(
        payload,
        doc_preview=0 if args.full else args.doc_preview,
        embedding_preview=0 if args.full or args.output else args.embedding_preview,
        full=bool(args.full or args.output),
    )

    result = {
        "persist_dir": str(persist_dir),
        "collection": args.collection,
        "include": include,
        "count": len(rows),
        "records": rows,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"已写入 {args.output}（{len(rows)} 条）")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

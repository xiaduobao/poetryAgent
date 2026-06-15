#!/usr/bin/env python3
"""离线构建向量索引。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.hf_bootstrap import bootstrap_hf_hub_env  # noqa: E402

_hf = bootstrap_hf_hub_env()
if _hf:
    print(f"Using HF mirror: {_hf}")

from app.rag.indexer import build_vector_store  # noqa: E402


def main():
    print("Building Chroma index...")
    vs = build_vector_store(force=True)
    count = vs._collection.count()  # noqa: SLF001
    print(f"Done. Documents in collection: {count}")


if __name__ == "__main__":
    main()

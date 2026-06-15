"""风格对比工具。"""
from typing import Any

from app.tools.author import query_author

# 预设对比维度
COMPARE_PRESETS: dict[str, dict[str, str]] = {
    ("李白", "杜甫"): {
        "summary": "李白豪放飘逸、想象奇崛；杜甫沉郁顿挫、忧国忧民。",
        "dimension": "浪漫主义 vs 现实主义",
        "language": "清新自然 vs 格律精严",
        "theme": "山水游仙、人生豪情 vs 民生疾苦、家国情怀",
    },
    ("苏轼", "李清照"): {
        "summary": "苏轼豪放旷达；李清照婉约细腻。",
        "dimension": "豪放派 vs 婉约派",
        "language": "开阔比喻 vs 白描细腻",
        "theme": "人生哲理、怀古 vs 闺情、离愁",
    },
}


def compare_styles(author_a: str, author_b: str) -> dict[str, Any]:
    """对比两位诗人的风格差异。"""
    key = (author_a, author_b)
    key_rev = (author_b, author_a)
    preset = COMPARE_PRESETS.get(key) or COMPARE_PRESETS.get(key_rev)

    info_a = query_author(author_a)
    info_b = query_author(author_b)

    result: dict[str, Any] = {
        "author_a": author_a,
        "author_b": author_b,
        "author_a_info": info_a.get("data") if info_a.get("found") else None,
        "author_b_info": info_b.get("data") if info_b.get("found") else None,
    }

    if preset:
        result["comparison"] = preset
        result["found"] = True
    else:
        result["found"] = bool(info_a.get("found") and info_b.get("found"))
        result["comparison"] = {
            "summary": f"请结合知识库检索 {author_a} 与 {author_b} 的代表作进行具体分析。",
            "dimension": "待 RAG 补充",
        }

    return result

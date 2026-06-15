"""创作辅助工具：提供格律指南与参考诗词。"""
from __future__ import annotations

from typing import Any

from app.tools.corpus_utils import get_parsed_corpus

WRITING_RULES: dict[str, dict[str, Any]] = {
    "五言绝句": {
        "line_count": 4,
        "chars_per_line": 5,
        "rhyme": "二四句押韵",
        "steps": [
            "确定主题与意境",
            "拟定韵脚字（二、四句末字同韵）",
            "先写起承转合四句骨架",
            "逐句润色对仗与意象",
        ],
    },
    "七言律诗": {
        "line_count": 8,
        "chars_per_line": 7,
        "rhyme": "偶句押韵（二四六八句）",
        "steps": [
            "确定主题与情感基调",
            "规划八句起承转合结构",
            "颔联、颈联注意对仗",
            "偶句末字押同一韵部",
        ],
    },
    "七言绝句": {
        "line_count": 4,
        "chars_per_line": 7,
        "rhyme": "二四句押韵",
        "steps": [
            "确定主题",
            "二四句末字押韵",
            "四句起承转合",
        ],
    },
    "填词": {
        "line_count": "依词牌而定",
        "chars_per_line": "依词牌而定",
        "rhyme": "依词牌格律",
        "steps": [
            "选定词牌（如《水调歌头》《念奴娇》）",
            "查阅词牌格律（句式、韵脚）",
            "按上下阕结构填词",
            "注意平仄与押韵位置",
        ],
    },
    "对联": {
        "line_count": 2,
        "chars_per_line": "上下联字数相等",
        "rhyme": "不要求押韵，要求对仗",
        "steps": [
            "确定主题",
            "上下联字数相等",
            "词性、结构对仗",
            "平仄相对（可宽对）",
        ],
    },
    "藏头诗": {
        "line_count": "依藏头字数",
        "chars_per_line": "通常五言或七言",
        "rhyme": "可绝句或律诗格律",
        "steps": [
            "确定要藏的字（如姓名、词语）",
            "每句首字依次为藏头字",
            "兼顾格律与意境",
        ],
    },
}


def _normalize_type(writing_type: str) -> str:
    t = writing_type.strip()
    for key in WRITING_RULES:
        if key in t or t in key:
            return key
    if "绝句" in t and "五" in t:
        return "五言绝句"
    if "绝句" in t and "七" in t:
        return "七言绝句"
    if "律诗" in t:
        return "七言律诗"
    if "词" in t:
        return "填词"
    if "对联" in t:
        return "对联"
    if "藏头" in t:
        return "藏头诗"
    return t


def _find_references(writing_type: str, theme: str, limit: int = 3) -> list[dict[str, str]]:
    norm = _normalize_type(writing_type)
    refs: list[dict[str, str]] = []

    genre_map = {
        "五言绝句": "五言",
        "七言绝句": "七言",
        "七言律诗": "律诗",
        "填词": "词",
    }
    genre_hint = genre_map.get(norm, "")

    for poem in get_parsed_corpus():
        score = 0
        genre = poem.get("genre", "")
        if genre_hint and genre_hint in genre:
            score += 3
        if theme and theme in poem.get("theme", ""):
            score += 4
        if theme and theme in poem.get("appreciation", ""):
            score += 2
        if score > 0:
            refs.append(
                {
                    "title": poem.get("title", ""),
                    "author": poem.get("author", ""),
                    "genre": genre,
                    "snippet": poem.get("original", "")[:60],
                    "source_file": poem.get("source_file", ""),
                    "_score": score,
                }
            )

    refs.sort(key=lambda x: x.pop("_score", 0), reverse=True)
    if not refs:
        for poem in get_parsed_corpus()[:limit]:
            refs.append(
                {
                    "title": poem.get("title", ""),
                    "author": poem.get("author", ""),
                    "genre": poem.get("genre", ""),
                    "snippet": poem.get("original", "")[:60],
                    "source_file": poem.get("source_file", ""),
                }
            )
    return refs[:limit]


def writing_guide(
    writing_type: str,
    theme: str = "",
    constraints: str = "",
) -> dict[str, Any]:
    """返回创作指南、格律要求与参考诗词。"""
    writing_type = writing_type.strip()
    if not writing_type:
        return {"found": False, "message": "请指定创作类型，如：五言绝句、对联、藏头诗。"}

    norm_type = _normalize_type(writing_type)
    rules = WRITING_RULES.get(norm_type)
    if not rules:
        rules = {
            "line_count": "依体裁而定",
            "chars_per_line": "依体裁而定",
            "rhyme": "请参考同类作品格律",
            "steps": ["明确体裁与主题", "查阅格律要求", "参考经典作品", "起草并润色"],
        }

    references = _find_references(norm_type, theme)
    checklist = list(rules.get("steps", []))
    if constraints:
        checklist.append(f"用户约束：{constraints}")

    return {
        "found": True,
        "writing_type": norm_type,
        "theme": theme,
        "constraints": constraints,
        "rules": {
            "line_count": rules.get("line_count"),
            "chars_per_line": rules.get("chars_per_line"),
            "rhyme": rules.get("rhyme"),
        },
        "checklist": checklist,
        "references": references,
        "note": "工具提供格律指南与参考，具体诗作由助手根据以上信息创作。",
    }

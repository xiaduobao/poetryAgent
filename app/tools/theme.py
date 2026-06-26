"""主题推荐工具：按情感/主题推荐诗词。"""
from __future__ import annotations

from typing import Any

from app.rag.retriever import get_hybrid_retriever
from app.tools.corpus_utils import get_parsed_corpus, parse_poem_doc

THEME_KEYWORDS: dict[str, list[str]] = {
    "思乡": ["思乡", "故乡", "归", "乡愁", "客"],
    "送别": ["送别", "离别", "赠", "送"],
    "怀古": ["怀古", "古迹", "赤壁", "历史", "兴亡"],
    "咏物": ["咏", "梅", "柳", "草", "物"],
    "闺情": ["闺", "相思", "离愁", "愁"],
    "边塞": ["边塞", "戍", "战", "征", "塞"],
    "哲理": ["人生", "哲理", "旷达", "感悟"],
    "爱国": ["家国", "忧国", "民", "国"],
    "爱情": ["相思", "情", "鹊桥", "爱情"],
    "春天": ["春", "花", "绿"],
    "秋天": ["秋", "落叶", "悲秋"],
}


def _expand_theme_keywords(theme: str) -> set[str]:
    keywords = {theme.strip()}
    for key, aliases in THEME_KEYWORDS.items():
        if key in theme or theme in key:
            keywords.add(key)
            keywords.update(aliases)
        for alias in aliases:
            if alias in theme or theme in alias:
                keywords.add(key)
                keywords.update(aliases)
    return {k for k in keywords if k}


def _score_poem(poem: dict[str, Any], keywords: set[str]) -> int:
    score = 0
    theme_text = poem.get("theme", "")
    searchable = " ".join(
        [
            poem.get("title", ""),
            poem.get("author", ""),
            theme_text,
            poem.get("appreciation", "")[:300],
        ]
    )
    for kw in keywords:
        if kw in theme_text:
            score += 5
        if kw in searchable:
            score += 2
    return score


def recommend_by_theme(theme: str, limit: int = 5) -> dict[str, Any]:
    """按主题/情感推荐诗词。"""
    theme = theme.strip()
    if not theme:
        return {"found": False, "message": "请提供主题或情感关键词，如：思乡、送别。"}

    keywords = _expand_theme_keywords(theme)
    scored: list[tuple[int, dict[str, Any]]] = []
    for poem in get_parsed_corpus():
        score = _score_poem(poem, keywords)
        if score > 0:
            scored.append((score, poem))

    seen_titles: set[str] = set()
    recommendations: list[dict[str, Any]] = []

    for score, poem in sorted(scored, key=lambda x: x[0], reverse=True):
        title = poem.get("title", "")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        snippet = poem.get("original", "")[:80] or poem.get("appreciation", "")[:120]
        recommendations.append(
            {
                "title": title,
                "author": poem.get("author", ""),
                "dynasty": poem.get("dynasty", ""),
                "theme": poem.get("theme", ""),
                "snippet": snippet,
                "source_file": poem.get("source_file", ""),
                "score": score,
            }
        )
        if len(recommendations) >= limit:
            break

    if not recommendations:
        try:
            retriever = get_hybrid_retriever()
            docs = retriever.retrieve(theme, profile="light")[:6]
            for doc in docs:
                poem = parse_poem_doc(doc)
                title = poem.get("title", "")
                if title in seen_titles:
                    continue
                seen_titles.add(title)
                recommendations.append(
                    {
                        "title": title,
                        "author": poem.get("author", ""),
                        "dynasty": poem.get("dynasty", ""),
                        "theme": poem.get("theme", ""),
                        "snippet": poem.get("original", "")[:80]
                        or poem.get("appreciation", "")[:120],
                        "source_file": poem.get("source_file", ""),
                        "score": 1,
                    }
                )
                if len(recommendations) >= limit:
                    break
        except Exception:
            pass

    if not recommendations:
        return {
            "found": False,
            "message": f"知识库中暂无与「{theme}」高度相关的诗词，可尝试其他主题词。",
        }

    return {
        "found": True,
        "theme": theme,
        "recommendations": recommendations[:limit],
    }

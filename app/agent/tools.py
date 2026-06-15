"""LangChain 工具定义（Function Calling）。"""
import json
from typing import Annotated

from langchain_core.tools import tool

from app.tools.allusion import explain_allusion as _explain_allusion
from app.tools.author import query_author as _query_author
from app.tools.compare import compare_styles as _compare_styles
from app.tools.meter import analyze_meter as _analyze_meter
from app.tools.poem_lookup import lookup_poem as _lookup_poem
from app.tools.theme import recommend_by_theme as _recommend_by_theme
from app.tools.writing import writing_guide as _writing_guide


@tool
def author_query(name: Annotated[str, "作者姓名，如：杜甫、李白"]) -> str:
    """查询作者生平、代表作、诗歌风格。"""
    result = _query_author(name)
    return json.dumps(result, ensure_ascii=False)


@tool
def meter_analysis(
    title: Annotated[str, "诗词标题，如：静夜思、登高"],
    content: Annotated[str, "可选，诗词原文"] = "",
) -> str:
    """分析诗词格律：体裁、句数、押韵、平仄示意。"""
    result = _analyze_meter(title, content)
    return json.dumps(result, ensure_ascii=False)


@tool
def style_compare(
    author_a: Annotated[str, "第一位作者"],
    author_b: Annotated[str, "第二位作者"],
) -> str:
    """对比两位诗人的风格差异。"""
    result = _compare_styles(author_a, author_b)
    return json.dumps(result, ensure_ascii=False)


@tool
def poem_lookup(
    title: Annotated[str, "诗题，如：枫桥夜泊、静夜思"] = "",
    author: Annotated[str, "可选，作者名"] = "",
) -> str:
    """按诗题或作者检索诗词原文、注释、译文。"""
    result = _lookup_poem(title, author)
    return json.dumps(result, ensure_ascii=False)


@tool
def theme_recommend(
    theme: Annotated[str, "主题或情感，如：思乡、送别、怀古"],
    limit: Annotated[int, "推荐数量，默认 5"] = 5,
) -> str:
    """按主题或情感推荐相关诗词。"""
    result = _recommend_by_theme(theme, limit=limit)
    return json.dumps(result, ensure_ascii=False)


@tool
def allusion_explain(
    query: Annotated[str, "诗句片段或典故名，如：渚、赤壁"],
) -> str:
    """解释诗句中的典故、地名、历史人物等。"""
    result = _explain_allusion(query)
    return json.dumps(result, ensure_ascii=False)


@tool
def writing_assistant(
    writing_type: Annotated[str, "创作类型：五言绝句、七言律诗、对联、藏头诗、填词等"],
    theme: Annotated[str, "创作主题，如：春天、思乡"] = "",
    constraints: Annotated[str, "可选约束，如藏头字、字数要求"] = "",
) -> str:
    """提供诗词创作指南、格律要求与参考作品，辅助用户创作。"""
    result = _writing_guide(writing_type, theme, constraints)
    return json.dumps(result, ensure_ascii=False)


AGENT_TOOLS = [
    author_query,
    meter_analysis,
    style_compare,
    poem_lookup,
    theme_recommend,
    allusion_explain,
    writing_assistant,
]

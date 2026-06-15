"""LangChain 工具定义（Function Calling）。"""
import json
from typing import Annotated

from langchain_core.tools import tool

from app.tools.author import query_author as _query_author
from app.tools.compare import compare_styles as _compare_styles
from app.tools.meter import analyze_meter as _analyze_meter


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


AGENT_TOOLS = [author_query, meter_analysis, style_compare]

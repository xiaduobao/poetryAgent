"""格律分析工具（五言/七言、押韵示意）。"""
import re
from typing import Any


# 简化平仄表（演示用，非完整韵书）
PINGZE_HINT = {
    "床": "平", "前": "平", "明": "平", "月": "仄", "光": "平",
    "疑": "平", "是": "仄", "地": "仄", "上": "仄", "霜": "平",
    "举": "仄", "头": "平", "望": "仄", "低": "平", "思": "平", "故": "仄", "乡": "平",
}


def _extract_lines_from_title_or_text(title: str, text: str = "") -> list[str]:
    """从用户输入或正文中提取诗句行。"""
    if text:
        lines = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip() and not ln.startswith("#") and "：" not in ln[:3]
        ]
        verse = [l for l in lines if re.search(r"[\u4e00-\u9fff]，", l) or len(l) <= 12]
        if verse:
            return verse[:4]
    return []


def analyze_meter(title: str, content: str = "") -> dict[str, Any]:
    """
    分析诗词格律：体裁、句数、字数、押韵字、平仄示意。
    """
    lines = _extract_lines_from_title_or_text(title, content)
    if not lines and "静夜思" in title:
        lines = [
            "床前明月光，疑是地上霜。",
            "举头望明月，低头思故乡。",
        ]
    if not lines and "登高" in title:
        lines = [
            "风急天高猿啸哀，渚清沙白鸟飞回。",
            "无边落木萧萧下，不尽长江滚滚来。",
            "万里悲秋常作客，百年多病独登台。",
            "艰难苦恨繁霜鬓，潦倒新停浊酒杯。",
        ]

    if not lines:
        return {
            "found": False,
            "message": "未能解析诗句，请提供诗题或完整原文。",
        }

    char_counts = [len(re.sub(r"[，。、；！？\s]", "", ln)) for ln in lines]
    avg = sum(char_counts) / len(char_counts) if char_counts else 0

    if avg <= 5:
        genre = "五言"
    elif avg <= 7:
        genre = "七言"
    else:
        genre = "长篇/词"

    if len(lines) == 4:
        form = f"{genre}绝句"
    elif len(lines) == 8:
        form = f"{genre}律诗"
    else:
        form = f"{genre}（{len(lines)}句）"

    rhyme_chars = []
    for ln in lines:
        m = re.search(r"([\u4e00-\u9fff])[。，！？]?$", ln.replace("，", ""))
        if m:
            rhyme_chars.append(m.group(1))

    pingze_sample = []
    for ln in lines[:2]:
        for ch in ln:
            if ch in PINGZE_HINT:
                pingze_sample.append(f"{ch}({PINGZE_HINT[ch]})")
        if len(pingze_sample) >= 8:
            break

    return {
        "found": True,
        "title": title,
        "form": form,
        "line_count": len(lines),
        "lines": lines,
        "rhyme_chars": rhyme_chars,
        "rhyme_note": "末字押韵（简化分析，完整平仄需韵书校验）",
        "pingze_sample": pingze_sample[:12] or ["示例平仄需结合具体韵部"],
    }

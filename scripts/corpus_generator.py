"""LLM 批量生成诗词语料 Markdown。"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import get_llm
from app.config import get_settings

logger = logging.getLogger(__name__)

CORPUS_TEMPLATE = """请为古典诗词知识库生成一篇完整的 Markdown 语料，要求严格如下。

## 诗词信息
- 诗题：{title}
- 作者：{author}
- 朝代：{dynasty}
- 体裁：{genre}

## 输出格式（必须严格遵守，不要输出任何多余说明）
第一行必须是标题行，格式 exactly：
# 《{title}》-{author}-{dynasty}-{genre}

然后依次包含以下二级标题区块（每个都必须有实质内容）：
## 原文
（完整原文，保留标点）
## 注释
（每条注释用 - 开头）
## 白话译文
（一段完整译文）
## 鉴赏
（200字以上的专业鉴赏，含艺术手法与情感）
## 元数据
- 作者：{author}
- 朝代：{dynasty}
- 体裁：{genre}
- 主题：（1-3个关键词）

注意：原文必须真实准确，不得编造不存在的历史诗词。若是词牌，诗题保留词牌名即可。
"""

LIST_BY_THEME_PROMPT = """请列出 {count} 首中国古典诗词，主题/意境与「{theme}」相关。
要求：唐诗宋词为主，作者各不相同，尽量经典名篇。
只输出 JSON 数组，无其他文字，格式：
[{{"title":"静夜思","author":"李白","dynasty":"唐","genre":"五言绝句"}}, ...]
"""

LIST_BY_DYNASTY_PROMPT = """请列出 {count} 首{dynasty}代经典诗词。
只输出 JSON 数组，无其他文字，格式：
[{{"title":"...","author":"...","dynasty":"{dynasty}","genre":"..."}}, ...]
"""

LIST_FAMOUS_TANG_SONG_PROMPT = """请列出 {count} 首唐宋时期（唐、五代、宋）最著名的经典诗词名篇。
要求：
- 唐诗与宋词兼顾，体裁多样（绝句、律诗、词等）
- 均为真实传世名篇，作者各不相同，尽量覆盖不同诗人
- 优先教材、鉴赏常引用的代表作
只输出 JSON 数组，无其他文字，格式：
[{{"title":"静夜思","author":"李白","dynasty":"唐","genre":"五言绝句"}}, ...]
"""

AUTHOR_PROMPT = """请为古代诗人「{name}」生成 JSON 资料，只输出 JSON 对象，无其他文字：
{{
  "name": "姓名",
  "dynasty": "朝代",
  "lifespan": "生卒年",
  "bio": "生平简介50字以上",
  "style": "风格特点",
  "masterpieces": ["代表作1","代表作2",...至少4个],
  "tags": ["标签1","标签2"]
}}
内容须符合史实，不得虚构诗人。"""

REQUIRED_SECTIONS = ("## 原文", "## 注释", "## 白话译文", "## 鉴赏", "## 元数据")


@dataclass
class PoemSpec:
    title: str
    author: str
    dynasty: str = ""
    genre: str = ""


def sanitize_filename(title: str, author: str) -> str:
    """生成语料文件名：诗题-作者.md"""
    t = re.sub(r"[《》\s/\\:*?\"<>|]", "", title)
    a = re.sub(r"[《》\s/\\:*?\"<>|]", "", author)
    return f"{t}-{a}.md"


def validate_corpus_markdown(content: str, spec: PoemSpec) -> list[str]:
    """校验生成内容，返回错误列表（空=通过）。"""
    errors: list[str] = []
    if not content.strip():
        errors.append("内容为空")
        return errors

    for sec in REQUIRED_SECTIONS:
        if sec not in content:
            errors.append(f"缺少区块: {sec}")

    if not re.search(
        rf"^#\s*《?{re.escape(spec.title)}》?[-－]{re.escape(spec.author)}",
        content,
        re.MULTILINE,
    ):
        errors.append("标题行与诗题/作者不匹配")

    # 去掉 markdown 代码块包裹
    if content.strip().startswith("```"):
        errors.append("不应包含 markdown 代码围栏")

    return errors


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def _invoke_llm(system: str, human: str, temperature: float = 0.2) -> str:
    llm = get_llm()
    if temperature != 0.2:
        llm = llm.bind(temperature=temperature)
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    return resp.content if hasattr(resp, "content") else str(resp)


def generate_poem_markdown(spec: PoemSpec, *, max_retries: int = 2) -> str:
    """调用 LLM 生成单篇语料 Markdown。"""
    dynasty = spec.dynasty or "待填"
    genre = spec.genre or "待填"
    system = (
        "你是严谨的古典文学专家，为诗词 RAG 知识库撰写结构化语料。"
        "输出必须是纯 Markdown，不要代码围栏，不要前言后语。"
    )
    human = CORPUS_TEMPLATE.format(
        title=spec.title,
        author=spec.author,
        dynasty=dynasty,
        genre=genre,
    )

    last_err: list[str] = []
    for attempt in range(max_retries + 1):
        content = _strip_code_fence(_invoke_llm(system, human))
        if attempt < max_retries and last_err:
            human = (
                CORPUS_TEMPLATE.format(
                    title=spec.title,
                    author=spec.author,
                    dynasty=spec.dynasty or "待填",
                    genre=spec.genre or "待填",
                )
                + f"\n\n上次生成不合格：{'; '.join(last_err)}。请修正后重新输出。"
            )
        last_err = validate_corpus_markdown(content, spec)
        if not last_err:
            return _normalize_header(content, spec)
        logger.warning("校验失败 %s (attempt %d): %s", spec.title, attempt + 1, last_err)

    raise ValueError(f"《{spec.title}》生成校验失败: {'; '.join(last_err)}")


def _normalize_header(content: str, spec: PoemSpec) -> str:
    """确保首行标题格式统一。"""
    dynasty = spec.dynasty or "未知"
    genre = spec.genre or "诗"
    header = f"# 《{spec.title}》-{spec.author}-{dynasty}-{genre}"
    lines = content.strip().splitlines()
    if lines and lines[0].startswith("#"):
        lines[0] = header
    else:
        lines.insert(0, header)
    return "\n".join(lines) + "\n"


def parse_batch_line(line: str) -> PoemSpec | None:
    """解析批量任务行：诗题,作者[,朝代][,体裁] 或 诗题|作者|朝代|体裁"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    sep = "|" if "|" in line else ","
    parts = [p.strip() for p in line.split(sep)]
    if len(parts) < 2:
        return None
    return PoemSpec(
        title=parts[0],
        author=parts[1],
        dynasty=parts[2] if len(parts) > 2 else "",
        genre=parts[3] if len(parts) > 3 else "",
    )


def load_batch_file(path: Path) -> list[PoemSpec]:
    specs: list[PoemSpec] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        spec = parse_batch_line(line)
        if spec:
            specs.append(spec)
    return specs


def _parse_json_array(text: str) -> list[dict]:
    text = text.strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        raise ValueError("LLM 未返回 JSON 数组")
    return json.loads(m.group())


def discover_poems_by_theme(theme: str, count: int) -> list[PoemSpec]:
    raw = _invoke_llm(
        "只输出 JSON，不要解释。",
        LIST_BY_THEME_PROMPT.format(theme=theme, count=count),
        temperature=0.5,
    )
    items = _parse_json_array(raw)
    return [_item_to_spec(x) for x in items[:count]]


def discover_poems_by_dynasty(dynasty: str, count: int) -> list[PoemSpec]:
    raw = _invoke_llm(
        "只输出 JSON，不要解释。",
        LIST_BY_DYNASTY_PROMPT.format(dynasty=dynasty, count=count),
        temperature=0.5,
    )
    items = _parse_json_array(raw)
    return [_item_to_spec(x) for x in items[:count]]


def discover_famous_poems(count: int) -> list[PoemSpec]:
    """从唐宋著名作品中由 LLM 选题，无需指定诗名。"""
    raw = _invoke_llm(
        "只输出 JSON，不要解释。",
        LIST_FAMOUS_TANG_SONG_PROMPT.format(count=count),
        temperature=0.5,
    )
    items = _parse_json_array(raw)
    return [_item_to_spec(x) for x in items[:count]]


def _item_to_spec(item: dict) -> PoemSpec:
    return PoemSpec(
        title=str(item.get("title", "")).strip(),
        author=str(item.get("author", "")).strip(),
        dynasty=str(item.get("dynasty", "")).strip(),
        genre=str(item.get("genre", "")).strip(),
    )


def save_corpus(content: str, spec: PoemSpec, *, force: bool = False) -> Path:
    settings = get_settings()
    out_dir = Path(settings.corpus_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / sanitize_filename(spec.title, spec.author)
    if path.exists() and not force:
        raise FileExistsError(f"已存在: {path}，使用 --force 覆盖")
    path.write_text(content, encoding="utf-8")
    return path


def generate_and_save(
    spec: PoemSpec,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> Path | None:
    logger.info("生成: 《%s》-%s", spec.title, spec.author)
    if dry_run:
        logger.info("[dry-run] 跳过写入")
        return None
    content = generate_poem_markdown(spec)
    return save_corpus(content, spec, force=force)


def batch_generate(
    specs: list[PoemSpec],
    *,
    force: bool = False,
    dry_run: bool = False,
    delay: float = 1.0,
    skip_existing: bool = True,
) -> tuple[list[Path], list[str]]:
    """批量生成，返回 (成功路径, 失败信息)。"""
    settings = get_settings()
    out_dir = Path(settings.corpus_dir)
    ok: list[Path] = []
    failed: list[str] = []

    for i, spec in enumerate(specs):
        if not spec.title or not spec.author:
            failed.append(f"无效条目: {spec}")
            continue
        path = out_dir / sanitize_filename(spec.title, spec.author)
        if skip_existing and path.exists() and not force:
            logger.info("跳过已存在: %s", path.name)
            continue
        try:
            p = generate_and_save(spec, force=force, dry_run=dry_run)
            if p:
                ok.append(p)
                logger.info("已写入: %s", p)
        except Exception as e:
            msg = f"《{spec.title}》-{spec.author}: {e}"
            logger.error(msg)
            failed.append(msg)
        if delay > 0 and i < len(specs) - 1:
            time.sleep(delay)
    return ok, failed


def generate_author_entry(name: str, *, force: bool = False) -> dict:
    """生成并合并作者到 authors.json。"""
    settings = get_settings()
    path = Path(settings.authors_db)
    db: dict = {}
    if path.exists():
        db = json.loads(path.read_text(encoding="utf-8"))

    if name in db and not force:
        logger.info("作者已存在: %s", name)
        return db[name]

    raw = _invoke_llm("只输出 JSON 对象。", AUTHOR_PROMPT.format(name=name))
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError(f"无法解析作者 JSON: {name}")
    entry = json.loads(m.group())
    key = entry.get("name", name)
    db[key] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("已更新 authors.json: %s", key)
    return entry

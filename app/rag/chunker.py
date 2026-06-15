"""按单首诗词+鉴赏分块，带标题锚定与重叠窗口。"""
import re
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings


def _parse_title_anchor(content: str, filename: str) -> dict:
    """从 Markdown 标题解析锚定元数据。"""
    meta = {"source_file": filename}
    m = re.search(r"^#\s*《?([^》]+)》?[-－]([^-－\n]+)", content, re.MULTILINE)
    if m:
        meta["title"] = m.group(1).strip()
        rest = m.group(2).strip()
        parts = re.split(r"[-－]", rest)
        if parts:
            meta["author"] = parts[0].strip()
        if len(parts) > 1:
            meta["dynasty"] = parts[1].strip()
        if len(parts) > 2:
            meta["genre"] = parts[2].strip()
    return meta


def _extract_metadata_section(content: str) -> dict:
    """解析文末元数据区块。"""
    extra = {}
    section = re.search(r"##\s*元数据\s*\n(.*?)(?:\n##|\Z)", content, re.DOTALL)
    if not section:
        return extra
    for line in section.group(1).strip().splitlines():
        if "：" in line or ":" in line:
            sep = "：" if "：" in line else ":"
            k, v = line.split(sep, 1)
            key = k.strip().lstrip("-").strip()
            extra[key] = v.strip()
    return extra


def load_poetry_documents(corpus_dir: str | Path) -> list[Document]:
    """加载语料目录下所有诗词 Markdown，每文件一块（语义完整）。"""
    corpus_path = Path(corpus_dir)
    docs: list[Document] = []
    for path in sorted(corpus_path.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        meta = _parse_title_anchor(content, path.name)
        meta.update(_extract_metadata_section(content))
        docs.append(
            Document(
                page_content=content,
                metadata=meta,
            )
        )
    return docs


def split_with_overlap(documents: list[Document]) -> list[Document]:
    """
    默认每首诗词保持单块；过长时按段落切分并保留重叠。
    重叠约 100 token（按字符近似 200 字）。
    """
    settings = get_settings()
    overlap_chars = settings.chunk_overlap_tokens * 2

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=overlap_chars,
        separators=["\n## ", "\n\n", "\n", "。"],
        length_function=len,
    )

    chunks: list[Document] = []
    for doc in documents:
        if len(doc.page_content) <= 1800:
            chunks.append(doc)
        else:
            for c in splitter.split_documents([doc]):
                c.metadata = {**doc.metadata, **c.metadata}
                chunks.append(c)
    return chunks

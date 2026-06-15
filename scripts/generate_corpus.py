#!/usr/bin/env python3
"""
通过 LLM 批量生成 data/corpus 语料文件。

用法示例：
  # 单首
  python scripts/generate_corpus.py single --title 春望 --author 杜甫

  # 批量（命令行）
  python scripts/generate_corpus.py batch --items "春望,杜甫,唐,七言律诗" "使至塞上,王维,唐,五言律诗"

  # 批量（任务文件）
  python scripts/generate_corpus.py batch --file data/poems_batch.txt

  # 按主题让 LLM 先选题再生成
  python scripts/generate_corpus.py theme --theme 思乡 --count 5

  # 按朝代选题生成
  python scripts/generate_corpus.py dynasty --dynasty 宋 --count 5

  # 自动从唐宋名篇选题生成（无需指定诗名，默认 20 篇）
  python scripts/generate_corpus.py auto
  python scripts/generate_corpus.py auto --count 10

  # 生成作者资料写入 authors.json
  python scripts/generate_corpus.py author --name 王维

  # 生成后重建向量索引
  python scripts/generate_corpus.py batch --file data/poems_batch.txt --rebuild-index
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.corpus_generator import (  # noqa: E402
    PoemSpec,
    batch_generate,
    discover_famous_poems,
    discover_poems_by_dynasty,
    discover_poems_by_theme,
    generate_and_save,
    generate_author_entry,
    load_batch_file,
    parse_batch_line,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("generate_corpus")


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--force", action="store_true", help="覆盖已存在文件")
    p.add_argument("--dry-run", action="store_true", help="只调用 LLM 校验，不写文件")
    p.add_argument("--delay", type=float, default=1.0, help="批量请求间隔秒数")
    p.add_argument("--no-skip", action="store_true", help="不跳过已存在文件（等同遇同名则失败）")
    p.add_argument(
        "--rebuild-index",
        action="store_true",
        help="完成后执行 scripts/build_index.py",
    )


def cmd_single(args: argparse.Namespace) -> int:
    spec = PoemSpec(
        title=args.title,
        author=args.author,
        dynasty=args.dynasty or "",
        genre=args.genre or "",
    )
    try:
        path = generate_and_save(spec, force=args.force, dry_run=args.dry_run)
        if path:
            logger.info("完成: %s", path)
        if args.rebuild_index and not args.dry_run:
            _rebuild_index()
        return 0
    except Exception as e:
        logger.error("%s", e)
        return 1


def cmd_batch(args: argparse.Namespace) -> int:
    specs: list[PoemSpec] = []
    if args.file:
        specs.extend(load_batch_file(Path(args.file)))
    for item in args.items or []:
        spec = parse_batch_line(item)
        if spec:
            specs.append(spec)
    if not specs:
        logger.error("未指定任务，请使用 --file 或 --items")
        return 1

    ok, failed = batch_generate(
        specs,
        force=args.force,
        dry_run=args.dry_run,
        delay=args.delay,
        skip_existing=not args.no_skip,
    )
    logger.info("成功 %d 篇，失败 %d 篇", len(ok), len(failed))
    for f in failed:
        logger.error("  %s", f)

    if args.rebuild_index and not args.dry_run and ok:
        _rebuild_index()
    return 0 if not failed else 1


def cmd_theme(args: argparse.Namespace) -> int:
    logger.info("按主题「%s」发现 %d 首诗...", args.theme, args.count)
    specs = discover_poems_by_theme(args.theme, args.count)
    if args.dry_run:
        for s in specs:
            logger.info("  - 《%s》%s %s %s", s.title, s.author, s.dynasty, s.genre)
        return 0
    ok, failed = batch_generate(
        specs,
        force=args.force,
        delay=args.delay,
        skip_existing=not args.no_skip,
    )
    logger.info("成功 %d，失败 %d", len(ok), len(failed))
    if args.rebuild_index and ok:
        _rebuild_index()
    return 0 if not failed else 1


def cmd_auto(args: argparse.Namespace) -> int:
    logger.info("从唐宋名篇自动发现 %d 首诗...", args.count)
    specs = discover_famous_poems(args.count)
    if args.dry_run:
        for s in specs:
            logger.info("  - 《%s》%s %s %s", s.title, s.author, s.dynasty, s.genre)
        return 0
    ok, failed = batch_generate(
        specs,
        force=args.force,
        delay=args.delay,
        skip_existing=not args.no_skip,
    )
    logger.info("成功 %d 篇，失败 %d 篇", len(ok), len(failed))
    for f in failed:
        logger.error("  %s", f)
    if args.rebuild_index and ok:
        _rebuild_index()
    return 0 if not failed else 1


def cmd_dynasty(args: argparse.Namespace) -> int:
    logger.info("按朝代「%s」发现 %d 首诗...", args.dynasty, args.count)
    specs = discover_poems_by_dynasty(args.dynasty, args.count)
    if args.dry_run:
        for s in specs:
            logger.info("  - 《%s》%s", s.title, s.author)
        return 0
    ok, failed = batch_generate(
        specs,
        force=args.force,
        delay=args.delay,
        skip_existing=not args.no_skip,
    )
    if args.rebuild_index and ok:
        _rebuild_index()
    return 0 if not failed else 1


def cmd_author(args: argparse.Namespace) -> int:
    try:
        generate_author_entry(args.name, force=args.force)
        return 0
    except Exception as e:
        logger.error("%s", e)
        return 1


def _rebuild_index() -> None:
    from app.rag.indexer import build_vector_store

    logger.info("重建向量索引...")
    build_vector_store(force=True)
    logger.info("索引重建完成")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="调用 LLM 批量生成诗词语料 Markdown（data/corpus）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # single
    p_single = sub.add_parser("single", help="生成单篇语料")
    p_single.add_argument("--title", required=True, help="诗题")
    p_single.add_argument("--author", required=True, help="作者")
    p_single.add_argument("--dynasty", default="", help="朝代，如：唐")
    p_single.add_argument("--genre", default="", help="体裁，如：七言律诗")
    _add_common_args(p_single)
    p_single.set_defaults(func=cmd_single)

    # batch
    p_batch = sub.add_parser("batch", help="按列表/文件批量生成")
    p_batch.add_argument(
        "--file",
        "-f",
        help="任务文件，每行：诗题,作者[,朝代][,体裁]",
    )
    p_batch.add_argument(
        "--items",
        "-i",
        nargs="*",
        help='命令行条目，如："春望,杜甫,唐,七言律诗"',
    )
    _add_common_args(p_batch)
    p_batch.set_defaults(func=cmd_batch)

    # theme
    p_theme = sub.add_parser("theme", help="按主题让 LLM 选题后批量生成")
    p_theme.add_argument("--theme", required=True, help="主题，如：思乡、豪放、边塞")
    p_theme.add_argument("--count", type=int, default=5, help="生成数量")
    _add_common_args(p_theme)
    p_theme.set_defaults(func=cmd_theme)

    # dynasty
    p_dynasty = sub.add_parser("dynasty", help="按朝代让 LLM 选题后批量生成")
    p_dynasty.add_argument("--dynasty", required=True, help="朝代：唐、宋、元、明、清")
    p_dynasty.add_argument("--count", type=int, default=5)
    _add_common_args(p_dynasty)
    p_dynasty.set_defaults(func=cmd_dynasty)

    # auto：唐宋名篇自动选题，无需诗名
    p_auto = sub.add_parser(
        "auto",
        help="从唐宋著名作品中由 LLM 自动选题并批量生成（无需指定诗名）",
    )
    p_auto.add_argument("--count", type=int, default=20, help="生成篇数，默认 20")
    _add_common_args(p_auto)
    p_auto.set_defaults(func=cmd_auto)

    # author
    p_author = sub.add_parser("author", help="生成作者资料到 authors.json")
    p_author.add_argument("--name", required=True, help="作者名")
    p_author.add_argument("--force", action="store_true")
    p_author.set_defaults(func=cmd_author)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

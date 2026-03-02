#!/usr/bin/env python3
"""为 memory_bench 章节文件构建索引。

该脚本会扫描 `memory_bench/data/source/raw/` 下的章节 Markdown，
尝试按章节 ID 关联 `memory_bench/data/source/norm/` 下的规范化文件，
并最终输出统一的 `index.json`。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from memory_bench.scripts.bench_logger import logger
from memory_bench.typing.index import IndexEntry, build_index_from_dir


def build_index(repo_root: Path) -> tuple[list[IndexEntry], list[str]]:
    """从 raw 与 norm 构建统一索引数据。

    Args:
        repo_root: 仓库根目录路径。

    Returns:
        一个二元组，包含：
          1. 章节索引列表（按章节号与文件名排序）；
          2. 缺失 norm 文件时产生的告警信息列表。

        每条索引记录都包含 `id`、非空 `raw_path` 与可空 `norm_path`。
    """
    raw_dir = repo_root / "memory_bench" / "data" / "source" / "raw"
    norm_dir = repo_root / "memory_bench" / "data" / "source" / "norm"

    index, _ = build_index_from_dir(raw_dir, norm_dir)

    # 添加详细警告信息
    detailed_warnings: list[str] = []
    for entry in index:
        if not entry.norm_path:
            detailed_warnings.append(f"missing norm file for {entry.id}: expected in memory_bench/data/source/norm/")

    return index, detailed_warnings


def slice_index(
    index: list[IndexEntry],
    *,
    limit: int | None = None,
    tail: int | None = None,
    offset: int | None = None,
) -> list[IndexEntry]:
    """对已排序的索引列表进行切片。

    切片顺序：先 offset → 再 tail / limit。
    ``--tail`` 与 ``--limit`` 互斥时 ``--tail`` 优先。

    Args:
        index: 按章节号排序的索引列表。
        limit: 保留前 N 条。
        tail: 保留最后 N 条（优先于 limit）。
        offset: 先跳过前 N 条。

    Returns:
        切片后的索引列表（不修改原列表）。
    """
    from memory_bench.typing.index import IndexSliceParams

    params = IndexSliceParams(limit=limit, tail=tail, offset=offset)
    return params.apply(index)


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        argparse.Namespace: 解析后的参数对象，包含 ``force`` 与 ``limit``。
    """

    parser = argparse.ArgumentParser(description="Build index.json for memory_bench chapter files.")
    parser.add_argument("--force", action="store_true", help="Force rebuild even if index exists")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only index the first N chapters (sorted by chapter number). "
        "Useful for quick testing without processing all data.",
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=None,
        help="Only index the last N chapters (sorted by chapter number). Useful for debugging newer chapters.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=None,
        help="Skip the first N chapters before applying --limit/--tail. Allows slicing from an arbitrary position.",
    )
    return parser.parse_args()


def main() -> None:
    """生成并写入 memory_bench 的 ``index.json``。

    支持三种切片方式（均在按章节号排序后生效）：

    - ``--limit N``：保留前 N 条。
    - ``--tail N``：保留最后 N 条（与 ``--limit`` 互斥，优先级更高）。
    - ``--offset N``：先跳过前 N 条，再应用 ``--limit`` 或 ``--tail``。

    切片后的索引写入 ``index.json``，下游脚本（annotate_all / compile_events）
    只处理索引中列出的章节。
    """

    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    output_path = repo_root / "memory_bench" / "data" / "source" / "index.json"

    index_data, build_warnings = build_index(repo_root)
    total_chapters = len(index_data)

    # --limit and --tail are mutually exclusive
    if args.limit is not None and args.tail is not None:
        log = logger.bind(group="memory")
        log.warning("--limit and --tail are mutually exclusive; --tail takes precedence")

    from memory_bench.typing.index import IndexSliceParams

    slice_params = IndexSliceParams(limit=args.limit, tail=args.tail, offset=args.offset)
    index_data = slice_params.apply(index_data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # pydantic v2: model_dump() 替代 dict()
    output_path.write_text(
        json.dumps([entry.model_dump() for entry in index_data], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    log = logger.bind(group="memory")
    slice_msg = slice_params.to_log_message()
    log.info(f"Generated index with {len(index_data)}/{total_chapters} chapters{slice_msg} -> {output_path}")
    for line in build_warnings:
        log.warning(line)


if __name__ == "__main__":
    main()

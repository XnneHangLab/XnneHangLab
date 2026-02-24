#!/usr/bin/env python3
"""为 memory_bench 章节文件构建索引。

该脚本会扫描 `memory_bench/data/source/raw/` 下的章节 Markdown，
尝试按章节 ID 关联 `memory_bench/data/source/norm/` 下的规范化文件，
并最终输出统一的 `index.json`。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import TypedDict

from memory_bench.scripts.bench_logger import logger

RAW_PATTERN = re.compile(r"^(ch\d{2,})_.*\.md$")
NORM_PATTERN = re.compile(r"^(ch\d{2,})_.*\.norm\.md$")


class IndexEntry(TypedDict):
    """单条章节索引记录。

    Attributes:
        id: 章节 ID，格式为 `chNN`（至少两位数字）。
        raw_path: 原始章节文件（raw）相对于仓库根目录的路径。
        norm_path: 规范化章节文件（norm）相对路径；若缺失则为空字符串。
    """

    id: str
    raw_path: str
    norm_path: str


def build_norm_map(repo_root: Path) -> dict[str, str]:
    """构建章节 ID 到规范化文件路径的映射。

    Args:
        repo_root: 仓库根目录路径。

    Returns:
        以章节 ID（`chNN`）为键、norm 文件相对路径为值的映射。
        若 norm 目录不存在，则返回空映射。
    """
    norm_dir = repo_root / "memory_bench" / "data" / "source" / "norm"
    norm_map: dict[str, str] = {}

    if not norm_dir.exists():
        return norm_map

    for file_path in norm_dir.iterdir():
        if not file_path.is_file():
            continue
        match = NORM_PATTERN.match(file_path.name)
        if not match:
            continue

        chapter_id = match.group(1)
        norm_map[chapter_id] = file_path.relative_to(repo_root).as_posix()

    return norm_map


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
    norm_map = build_norm_map(repo_root)
    entries: list[tuple[int, str, str, str]] = []
    warnings: list[str] = []

    for file_path in raw_dir.iterdir():
        if not file_path.is_file():
            continue
        match = RAW_PATTERN.match(file_path.name)
        if not match:
            continue

        chapter_id = match.group(1)
        chapter_num = int(chapter_id[2:])
        raw_path = file_path.relative_to(repo_root).as_posix()
        norm_path = norm_map.get(chapter_id, "")

        if not norm_path:
            warnings.append(f"missing norm file for {chapter_id}: expected in memory_bench/data/source/norm/")

        entries.append((chapter_num, chapter_id, raw_path, norm_path))

    entries.sort(key=lambda item: (item[0], Path(item[2]).name))

    index: list[IndexEntry] = [
        {
            "id": chapter_id,
            "raw_path": raw_path,
            "norm_path": norm_path,
        }
        for _, chapter_id, raw_path, norm_path in entries
    ]

    return index, warnings


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
    return parser.parse_args()


def main() -> None:
    """生成并写入 memory_bench 的 ``index.json``。

    当指定 ``--limit N`` 时，仅保留按章节号排序后的前 N 条索引记录，
    从而让下游 ``compile_events`` 只处理有限的章节数据。
    """

    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    output_path = repo_root / "memory_bench" / "data" / "source" / "index.json"

    index_data, warnings = build_index(repo_root)

    if args.limit is not None and args.limit > 0:
        index_data = index_data[: args.limit]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    log = logger.bind(group="memory")
    limit_msg = f" (limited to first {args.limit})" if args.limit is not None else ""
    log.info(f"Generated index with {len(index_data)} chapters{limit_msg} -> {output_path}")
    for line in warnings:
        log.warning(line)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""输出目录下最新匹配文件路径（按 glob）。"""

from __future__ import annotations

import argparse
from pathlib import Path

from memory_bench.scripts.bench_logger import logger

DEFAULT_EXPORT_DIR = Path("memory_bench/logs/replay_mem0")
DEFAULT_GLOB = "export_*.jsonl"


def find_latest_file(export_dir: Path, pattern: str = DEFAULT_GLOB) -> Path:
    """从目录中选择时间线上最新的匹配文件。

    Args:
        export_dir: 搜索目录。
        pattern: glob 匹配模式。

    Returns:
        最新匹配文件的路径。

    Raises:
        FileNotFoundError: 目录下无匹配文件。
    """
    candidates = [path for path in export_dir.glob(pattern) if path.is_file()]
    if not candidates:
        logger.error("目录 %s 下未找到匹配 '%s' 的文件", export_dir, pattern)
        raise FileNotFoundError(f"no {pattern} found in {export_dir}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def find_latest_export(export_dir: Path) -> Path:
    """兼容旧调用：选择最新 ``export_*.jsonl``。

    Args:
        export_dir: 搜索目录。

    Returns:
        最新 export JSONL 文件的路径。
    """
    return find_latest_file(export_dir=export_dir, pattern=DEFAULT_GLOB)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        argparse.ArgumentParser: 配置好的参数解析器实例。
    """
    parser = argparse.ArgumentParser(
        description="Print latest file path in directory by glob pattern",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--export-dir", type=str)
    parser.add_argument(
        "--glob",
        type=str,
        default=DEFAULT_GLOB,
        help="Glob pattern used to select latest file (e.g. export_*.jsonl / claims_nodes_*.jsonl)",
    )
    return parser


def main() -> int:
    """命令行入口。"""
    args = build_parser().parse_args()
    export_dir = Path(args.export_dir) if args.export_dir else DEFAULT_EXPORT_DIR
    latest_path = find_latest_file(export_dir, pattern=args.glob)
    logger.bind(group="memory").info(f"latest file selected: {latest_path} (glob={args.glob})")
    print(str(latest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

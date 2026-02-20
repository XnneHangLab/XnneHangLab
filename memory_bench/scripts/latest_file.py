#!/usr/bin/env python3
"""输出目录下最新匹配文件路径（按 glob）。"""

from __future__ import annotations

import argparse
from pathlib import Path

from memory_bench.scripts.bench_logger import logger

DEFAULT_EXPORT_DIR = Path("memory_bench/logs/replay_mem0")
DEFAULT_GLOB = "export_*.jsonl"


def find_latest_file(export_dir: Path, pattern: str = DEFAULT_GLOB) -> Path:
    """从目录中选择时间线上最新的匹配文件。"""

    candidates = [path for path in export_dir.glob(pattern) if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"no {pattern} found in {export_dir}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def find_latest_export(export_dir: Path) -> Path:
    """兼容旧调用：选择最新 ``export_*.jsonl``。"""

    return find_latest_file(export_dir=export_dir, pattern=DEFAULT_GLOB)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print latest file path in directory by glob pattern",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--export-dir", type=str, default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument(
        "--glob",
        type=str,
        default=DEFAULT_GLOB,
        help="Glob pattern used to select latest file (e.g. export_*.jsonl / claims_nodes_*.jsonl)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    latest_path = find_latest_file(Path(args.export_dir), pattern=args.glob)
    logger.bind(group="memory").info(f"latest file selected: {latest_path} (glob={args.glob})")
    print(str(latest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

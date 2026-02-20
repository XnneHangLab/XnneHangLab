#!/usr/bin/env python3
"""输出目录下时间线最新的 replay_mem0 export JSONL 文件路径。"""

from __future__ import annotations

import argparse
from pathlib import Path

from memory_bench.scripts.bench_logger import logger

DEFAULT_EXPORT_DIR = Path("memory_bench/logs/replay_mem0")


def find_latest_export(export_dir: Path) -> Path:
    """从目录中选择时间线上最新的 export_*.jsonl 文件。"""

    candidates = [path for path in export_dir.glob("export_*.jsonl") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"no export_*.jsonl found in {export_dir}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description="Print latest replay_mem0 export JSONL path",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--export-dir", type=str, default=str(DEFAULT_EXPORT_DIR))
    return parser


def main() -> int:
    """命令行入口。"""

    args = build_parser().parse_args()
    latest_path = find_latest_export(Path(args.export_dir))
    logger.bind(group="memory").info(f"latest export selected: {latest_path}")
    print(str(latest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

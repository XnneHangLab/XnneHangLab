#!/usr/bin/env python3
"""使用 replay_mem0 最新 export 文件运行 graphify pipeline。"""

from __future__ import annotations

import argparse
from pathlib import Path

from memory_bench.scripts.bench_logger import logger
from memory_bench.scripts.graphify_pipeline import run_pipeline

DEFAULT_EXPORT_DIR = Path("memory_bench/logs/replay_mem0")
DEFAULT_OUT_DIR = Path("memory_bench/logs/replay_mem0/graphify")
DEFAULT_STATE_DB = Path("memory_bench/state/graphify/state.sqlite")


def find_latest_export(export_dir: Path) -> Path:
    """从目录中选择时间线上最新的 export_*.jsonl 文件。"""

    candidates = [
        path
        for path in export_dir.glob("export_*.jsonl")
        if path.is_file()
    ]
    if not candidates:
        raise FileNotFoundError(f"no export_*.jsonl found in {export_dir}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description="Run graphify pipeline using the latest replay_mem0 export JSONL",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--export-dir", type=str, default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--state-db", type=str, default=str(DEFAULT_STATE_DB))
    parser.add_argument("--prefix", type=str, default="graph")
    parser.add_argument("--format", choices=("jsonl", "jsonl+csv"), default="jsonl")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--max-warnings", type=int, default=100)
    parser.add_argument("--warn-duplicate-keys", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--cypher-out-dir",
        type=str,
        default=None,
        help="Directory for neo4j cypher outputs (default: <out-dir>/neo4j)",
    )
    parser.add_argument(
        "--cypher",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable neo4j_export_cypher step. Default: enabled.",
    )
    return parser


def main() -> int:
    """命令行入口。"""

    args = build_parser().parse_args()

    export_dir = Path(args.export_dir)
    input_path = find_latest_export(export_dir)
    out_dir = Path(args.out_dir)
    cypher_out_dir = Path(args.cypher_out_dir) if args.cypher_out_dir else out_dir / "neo4j"

    logger.bind(group="memory").info(f"latest export selected: {input_path}")

    graph_artifacts, export_artifacts = run_pipeline(
        command="run",
        input_path=input_path,
        out_dir=out_dir,
        state_db=Path(args.state_db),
        prefix=args.prefix,
        output_format=args.format,
        strict=bool(args.strict),
        max_warnings=max(0, int(args.max_warnings)),
        warn_duplicate_keys=bool(args.warn_duplicate_keys),
        cypher_out_dir=cypher_out_dir,
        skip_cypher=not bool(args.cypher),
    )

    logger.bind(group="memory").info(f"graphify report: {graph_artifacts.report_path}")
    if export_artifacts is not None:
        logger.bind(group="memory").info(f"neo4j export report: {export_artifacts.report_path}")
    else:
        logger.bind(group="memory").info("neo4j export skipped (cypher disabled)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

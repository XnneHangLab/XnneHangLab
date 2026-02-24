#!/usr/bin/env python3
"""输出目录下最新匹配文件路径（按 glob）。"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from memory_bench.scripts.bench_logger import logger

DEFAULT_EXPORT_DIR = Path("memory_bench/logs/replay_mem0")
DEFAULT_GLOB = "export_*.jsonl"


@dataclass(frozen=True)
class PairKindSpec:
    """描述一种配对类型：锚点 glob、配对模板与默认目录。"""

    anchor_glob: str
    pair_template: str
    default_dir: str


PAIR_KINDS: dict[str, PairKindSpec] = {
    "cypher": PairKindSpec(
        anchor_glob="graph_constraints_*.cypher",
        pair_template="graph_import_{ts}.cypher",
        default_dir="memory_bench/logs/replay_mem0/graphify/neo4j",
    ),
}


def find_latest_file(export_dir: Path, pattern: str = DEFAULT_GLOB) -> Path:
    """从目录中选择时间线上最新的匹配文件。"""

    candidates = [path for path in export_dir.glob(pattern) if path.is_file()]
    if not candidates:
        logger.error("目录 %s 下未找到匹配 '%s' 的文件", export_dir, pattern)
        raise FileNotFoundError(f"no {pattern} found in {export_dir}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def find_latest_export(export_dir: Path) -> Path:
    """兼容旧调用：选择最新 ``export_*.jsonl``。"""

    return find_latest_file(export_dir=export_dir, pattern=DEFAULT_GLOB)


def find_latest_pair(export_dir: Path, kind: str) -> tuple[Path, Path]:
    """按配对规则选择最新可用的锚点文件与配对文件。"""

    spec = PAIR_KINDS.get(kind)
    if spec is None:
        raise ValueError(f"unknown pair kind: {kind}")

    parts = spec.anchor_glob.split("*")
    if len(parts) != 2:
        raise ValueError(f"anchor glob must contain exactly one '*': {spec.anchor_glob}")
    prefix, suffix = parts

    anchors = [path for path in export_dir.glob(spec.anchor_glob) if path.is_file()]
    anchors.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)

    for anchor_path in anchors:
        name = anchor_path.name
        if not name.startswith(prefix):
            continue
        if suffix and not name.endswith(suffix):
            continue
        end = len(name) - len(suffix) if suffix else len(name)
        ts = name[len(prefix) : end]
        if not re.fullmatch(r"\d{8}_\d{6}", ts):
            continue

        pair_path = export_dir / spec.pair_template.format(ts=ts)
        if pair_path.is_file():
            return anchor_path, pair_path

    logger.error(
        "目录 %s 下未找到 kind='%s' 的有效配对文件（anchor glob: '%s'）。"
        "请确认目录中存在形如 %s 的文件，且对应的 %s 也存在。",
        export_dir,
        kind,
        spec.anchor_glob,
        spec.anchor_glob,
        spec.pair_template.format(ts="YYYYMMDD_HHMMSS"),
    )
    raise FileNotFoundError(f"no valid pair found in {export_dir} for kind={kind}")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description="Print latest file path in directory by glob pattern",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--export-dir", type=str)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--glob",
        type=str,
        default=DEFAULT_GLOB,
        help="Glob pattern used to select latest file (e.g. export_*.jsonl / claims_nodes_*.jsonl)",
    )
    group.add_argument(
        "--pair-kind",
        type=str,
        choices=list(PAIR_KINDS.keys()),
        help="Pair kind used to find latest timestamped file pair",
    )
    return parser


def main() -> int:
    """命令行入口。"""

    args = build_parser().parse_args()
    if args.pair_kind:
        export_dir = Path(args.export_dir) if args.export_dir else Path(PAIR_KINDS[args.pair_kind].default_dir)
        anchor_path, pair_path = find_latest_pair(export_dir, args.pair_kind)
        logger.bind(group="memory").info(
            f"latest pair selected: anchor={anchor_path}, pair={pair_path} (kind={args.pair_kind})"
        )
        print(str(anchor_path))
        print(str(pair_path))
        return 0

    export_dir = Path(args.export_dir) if args.export_dir else DEFAULT_EXPORT_DIR
    latest_path = find_latest_file(export_dir, pattern=args.glob)
    logger.bind(group="memory").info(f"latest file selected: {latest_path} (glob={args.glob})")
    print(str(latest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

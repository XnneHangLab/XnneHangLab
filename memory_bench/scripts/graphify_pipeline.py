#!/usr/bin/env python3
"""Graphify V0 一体化流水线入口。

该模块通过复用既有 `graphify_export` 与 `neo4j_export_cypher`，提供
可重跑、可复位、默认幂等的命令行工作流。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from memory_bench.scripts.bench_logger import logger
from memory_bench.scripts.graphify_export import GraphArtifacts, run_graphify
from memory_bench.scripts.neo4j_export_cypher import ExportArtifacts, run_export

DEFAULT_OUT_DIR = Path("memory_bench/logs/replay_mem0/graphify")
DEFAULT_STATE_DB = Path("memory_bench/state/graphify/state.sqlite")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        argparse.ArgumentParser: 已注册 `run`、`dry-run`、`reset` 子命令的解析器。
    """

    parser = argparse.ArgumentParser(
        description="Run graphify_export + neo4j_export_cypher as an idempotent V0 pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset_parser = subparsers.add_parser("reset", help="Reset graphify state")
    reset_parser.add_argument("--state-db", type=str, default=str(DEFAULT_STATE_DB))
    reset_parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    reset_parser.add_argument("--reset-output", action="store_true")

    run_parser = subparsers.add_parser("run", help="run graphify pipeline")
    run_parser.add_argument("--input", type=str, required=True)
    run_parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    run_parser.add_argument("--state-db", type=str, default=str(DEFAULT_STATE_DB))
    run_parser.add_argument("--prefix", type=str, default="graph")
    run_parser.add_argument("--format", choices=("jsonl", "jsonl+csv"), default="jsonl")
    run_parser.add_argument("--strict", action="store_true")
    run_parser.add_argument("--max-warnings", type=int, default=100)
    run_parser.add_argument("--warn-duplicate-keys", action=argparse.BooleanOptionalAction, default=None)
    run_parser.add_argument(
        "--cypher-out-dir",
        type=str,
        default=None,
        help="Directory for neo4j cypher outputs (default: <out-dir>/neo4j)",
    )
    run_parser.add_argument(
        "--cypher",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable neo4j_export_cypher step. Default: enabled. Use --no-cypher to skip.",
    )

    dry_run_parser = subparsers.add_parser("dry-run", help="dry-run graphify pipeline")
    dry_run_parser.add_argument("--input", type=str, required=True)
    dry_run_parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    dry_run_parser.add_argument("--state-db", type=str, default=str(DEFAULT_STATE_DB))
    dry_run_parser.add_argument("--prefix", type=str, default="graph")
    dry_run_parser.add_argument("--format", choices=("jsonl", "jsonl+csv"), default="jsonl")
    dry_run_parser.add_argument("--strict", action="store_true")
    dry_run_parser.add_argument("--max-warnings", type=int, default=100)
    dry_run_parser.add_argument("--warn-duplicate-keys", action=argparse.BooleanOptionalAction, default=None)
    dry_run_parser.add_argument(
        "--cypher-out-dir",
        type=str,
        default=None,
        help="Directory for neo4j cypher outputs (default: <out-dir>/neo4j)",
    )

    return parser


def resolve_skip_cypher(command: str, cypher_flag: bool | None) -> bool:
    """解析是否跳过 cypher 导出步骤。

    默认行为：
    - `run`: 导出 cypher（可用 `--no-cypher` 关闭）
    - `dry-run`: 始终跳过 cypher（不支持 `--cypher`）

    Args:
        command: 当前子命令，支持 `run` 或 `dry-run`。
        cypher_flag: `run` 子命令下来自 `--cypher/--no-cypher` 的显式开关。

    Returns:
        bool: True 表示跳过 cypher 导出；False 表示执行 cypher 导出。
    """

    if command == "dry-run":
        return True
    if cypher_flag is None:
        return False
    return not bool(cypher_flag)


def print_next_steps(export_artifacts: ExportArtifacts) -> None:
    """打印 Neo4j 导入后的下一步说明。

    Args:
        export_artifacts: Cypher 导出产物对象，包含约束与导入脚本路径。
    """

    constraints = export_artifacts.constraints_path
    import_path = export_artifacts.import_path
    if constraints is None or import_path is None:
        return

    logger.info("=== Next steps (Neo4j) ===")
    logger.info(f"1) Run constraints: {constraints}")
    logger.info(f"2) Run import script: {import_path}")
    logger.info("3) Validate in Neo4j Browser:")
    logger.info("   MATCH (n:Node) RETURN count(n) AS node_count;")
    logger.info("   MATCH ()-[r:REL]->() RETURN count(r) AS rel_count;")


def run_pipeline(
    command: str,
    input_path: Path,
    out_dir: Path,
    state_db: Path,
    prefix: str,
    output_format: str,
    strict: bool,
    max_warnings: int,
    warn_duplicate_keys: bool,
    cypher_out_dir: Path,
    skip_cypher: bool,
) -> tuple[GraphArtifacts, ExportArtifacts | None]:
    """执行 pipeline 的主流程。

    Args:
        command: 子命令，支持 `run` 与 `dry-run`。
        input_path: replay 导出的 JSONL 输入路径。
        out_dir: graphify 输出目录。
        state_db: graphify 增量状态数据库路径。
        prefix: graph/cypher 文件前缀。
        output_format: graphify 输出格式（`jsonl` 或 `jsonl+csv`）。
        strict: 是否启用严格模式。
        max_warnings: 最多保留 warning 条数。
        warn_duplicate_keys: 是否记录重复 processed_key warning。
        cypher_out_dir: neo4j cypher 输出目录。
        skip_cypher: 是否跳过 cypher 导出。

    Returns:
        tuple[GraphArtifacts, ExportArtifacts | None]:
            graphify 产物与可选的 cypher 导出产物。
    """

    graphify_command = "add" if command == "run" else "dry-run"
    graph_artifacts = run_graphify(
        command=graphify_command,
        input_path=input_path,
        out_dir=out_dir,
        state_db=state_db,
        output_format=output_format,
        strict=strict,
        prefix=prefix,
        max_warnings=max(0, int(max_warnings)),
        warn_duplicate_keys=warn_duplicate_keys,
    )

    if skip_cypher:
        return graph_artifacts, None

    if graph_artifacts.nodes_path is None or graph_artifacts.edges_path is None:
        raise ValueError(
            "cypher export requires graph nodes/edges artifacts; "
            "for dry-run use default --no-cypher, or use `run --cypher` to generate cypher files"
        )

    export_artifacts = run_export(
        nodes_path=graph_artifacts.nodes_path,
        edges_path=graph_artifacts.edges_path,
        out_dir=cypher_out_dir,
        prefix=prefix,
        dry_run=False,
    )
    return graph_artifacts, export_artifacts


def main() -> int:
    """命令行入口函数。

    Returns:
        int: 退出码；成功返回 0。
    """

    args = build_parser().parse_args()

    if args.command == "reset":
        from memory_bench.scripts.graphify_export import reset_state

        reset_state(
            state_db=Path(args.state_db),
            reset_output=bool(args.reset_output),
            out_dir=Path(args.out_dir),
        )
        return 0

    out_dir = Path(args.out_dir)
    cypher_out_dir = Path(args.cypher_out_dir) if args.cypher_out_dir else out_dir / "neo4j"
    warn_duplicate_keys = (
        (args.command == "run") if args.warn_duplicate_keys is None else bool(args.warn_duplicate_keys)
    )
    skip_cypher = resolve_skip_cypher(command=args.command, cypher_flag=getattr(args, "cypher", None))

    graph_artifacts, export_artifacts = run_pipeline(
        command=args.command,
        input_path=Path(args.input),
        out_dir=out_dir,
        state_db=Path(args.state_db),
        prefix=args.prefix,
        output_format=args.format,
        strict=bool(args.strict),
        max_warnings=max(0, int(args.max_warnings)),
        warn_duplicate_keys=warn_duplicate_keys,
        cypher_out_dir=cypher_out_dir,
        skip_cypher=skip_cypher,
    )

    logger.info(f"graphify report: {graph_artifacts.report_path}")
    if export_artifacts is not None:
        logger.info(f"neo4j export report: {export_artifacts.report_path}")
        print_next_steps(export_artifacts)
    else:
        logger.info("neo4j export skipped (cypher disabled)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""V0 pipeline: 串联 graphify_export 与 neo4j_export_cypher。"""

from __future__ import annotations

import argparse
from pathlib import Path

from graphify_export import GraphArtifacts, run_graphify
from neo4j_export_cypher import ExportArtifacts, run_export

DEFAULT_OUT_DIR = Path("memory_bench/logs/replay_mem0/graphify")
DEFAULT_STATE_DB = Path("memory_bench/state/graphify/state.sqlite")


def build_parser() -> argparse.ArgumentParser:
    """构建参数解析器。"""

    parser = argparse.ArgumentParser(
        description="Run graphify_export + neo4j_export_cypher as an idempotent V0 pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset_parser = subparsers.add_parser("reset", help="Reset graphify state")
    reset_parser.add_argument("--state-db", type=str, default=str(DEFAULT_STATE_DB))
    reset_parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    reset_parser.add_argument("--reset-output", action="store_true")

    for cmd in ("run", "dry-run"):
        cmd_parser = subparsers.add_parser(cmd, help=f"{cmd} graphify pipeline")
        cmd_parser.add_argument("--input", type=str, required=True)
        cmd_parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
        cmd_parser.add_argument("--state-db", type=str, default=str(DEFAULT_STATE_DB))
        cmd_parser.add_argument("--prefix", type=str, default="graph")
        cmd_parser.add_argument("--format", choices=("jsonl", "jsonl+csv"), default="jsonl")
        cmd_parser.add_argument("--strict", action="store_true")
        cmd_parser.add_argument("--max-warnings", type=int, default=100)
        cmd_parser.add_argument("--warn-duplicate-keys", action=argparse.BooleanOptionalAction, default=None)
        cmd_parser.add_argument(
            "--cypher-out-dir",
            type=str,
            default=None,
            help="Directory for neo4j cypher outputs (default: <out-dir>/neo4j)",
        )
        cmd_parser.add_argument(
            "--cypher",
            action=argparse.BooleanOptionalAction,
            default=None,
            help=(
                "Enable/disable neo4j_export_cypher step. "
                "Defaults: run=True, dry-run=False. "
                "Use --cypher to force, --no-cypher to skip."
            ),
        )

    return parser


def resolve_skip_cypher(command: str, cypher_flag: bool | None) -> bool:
    """解析 cypher 导出开关。

    默认行为：
    - run: 导出 cypher
    - dry-run: 跳过 cypher（更符合 dry-run 语义）
    """

    if cypher_flag is None:
        return command == "dry-run"
    return not bool(cypher_flag)


def print_next_steps(export_artifacts: ExportArtifacts) -> None:
    """打印 Neo4j 下一步操作说明。"""

    constraints = export_artifacts.constraints_path
    import_path = export_artifacts.import_path
    if constraints is None or import_path is None:
        return

    print("\n=== Next steps (Neo4j) ===")
    print(f"1) Run constraints: {constraints}")
    print(f"2) Run import script: {import_path}")
    print("3) Validate in Neo4j Browser:")
    print("   MATCH (n:Node) RETURN count(n) AS node_count;")
    print("   MATCH ()-[r:REL]->() RETURN count(r) AS rel_count;")


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
    """执行 run/dry-run pipeline。"""

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
    """CLI 入口。"""

    args = build_parser().parse_args()

    if args.command == "reset":
        from graphify_export import reset_state

        reset_state(
            state_db=Path(args.state_db),
            reset_output=bool(args.reset_output),
            out_dir=Path(args.out_dir),
        )
        return 0

    out_dir = Path(args.out_dir)
    cypher_out_dir = Path(args.cypher_out_dir) if args.cypher_out_dir else out_dir / "neo4j"
    warn_duplicate_keys = (args.command == "run") if args.warn_duplicate_keys is None else bool(args.warn_duplicate_keys)
    skip_cypher = resolve_skip_cypher(command=args.command, cypher_flag=args.cypher)

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

    print(f"graphify report: {graph_artifacts.report_path}")
    if export_artifacts is not None:
        print(f"neo4j export report: {export_artifacts.report_path}")
        print_next_steps(export_artifacts)
    else:
        print("neo4j export skipped (--no-cypher)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

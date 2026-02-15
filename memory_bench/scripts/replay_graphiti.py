#!/usr/bin/env python3
"""将 Memory Bench 事件回放写入图谱后端（Neo4j 默认，预留 Cognee/Zep 接口）。"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bench_logger import logger
from graph_backend import GraphBackendConfig, GraphBackendError, create_graph_backend

if TYPE_CHECKING:
    from collections.abc import Iterator


class ReplayGraphError(RuntimeError):
    """表示 graph replay 过程中的输入或配置错误。"""


@dataclass(slots=True)
class ReplayGraphStats:
    total_events: int = 0
    ingested_events: int = 0
    skipped_existing_events: int = 0
    canon_facts: int = 0
    episodic_nodes: int = 0
    total_memory_items: int = 0
    ingested_memory_items: int = 0


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def parse_csv_arg(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(",") if part.strip()}


def resolve_neo4j_uri(memory_system: str, explicit_uri: str) -> str:
    if explicit_uri.strip():
        return explicit_uri.strip()

    system = memory_system.strip().lower()
    by_system = {
        "mem0": get_env("NEO4J_URI_MEM0"),
        "zep": get_env("NEO4J_URI_ZEP"),
        "cognee": get_env("NEO4J_URI_COGNEE"),
    }
    if by_system.get(system):
        return str(by_system[system])

    return get_env("NEO4J_URI", "bolt://127.0.0.1:7687") or "bolt://127.0.0.1:7687"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay benchmark events into graph backend",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", type=str, default="memory_bench/data/events/compiled/all.jsonl", help="Input JSONL (events or memory items)")
    parser.add_argument("--mode", choices=["events", "memory_items"], default="events", help="Graph replay input mode")
    parser.add_argument(
        "--backend",
        choices=["neo4j"],
        default=get_env("GRAPH_BACKEND", "neo4j"),
        help="Graph storage backend (Neo4j only)",
    )
    parser.add_argument("--neo4j-uri", type=str, default=get_env("NEO4J_URI", ""), help="Neo4j Bolt URI")
    parser.add_argument("--neo4j-user", type=str, default=get_env("NEO4J_USER", "neo4j"), help="Neo4j username")
    parser.add_argument(
        "--neo4j-password", type=str, default=get_env("NEO4J_PASSWORD", "neo4jneo4j"), help="Neo4j password"
    )
    parser.add_argument("--database", type=str, default=get_env("NEO4J_DATABASE", "neo4j"), help="Database name (base or explicit)")
    parser.add_argument(
        "--memory-system",
        choices=["mem0", "zep", "cognee"],
        default=get_env("MEMORY_SYSTEM", "mem0"),
        help="Memory system namespace for graph isolation",
    )
    parser.add_argument(
        "--graph-name",
        type=str,
        default=get_env("GRAPH_NAME", ""),
        help="Optional explicit graph/database name override",
    )
    parser.add_argument("--skip-role", type=str, default="ui,tool", help="Comma separated role_type values to skip")
    parser.add_argument("--skip-tags", type=str, default="filler", help="Comma separated tags to skip")
    parser.add_argument("--only-tags", type=str, default="", help="Optional allow-list tags")
    parser.add_argument("--clear", action="store_true", help="Clear graph before replay")
    parser.add_argument("--dry-run", action="store_true", help="Validate and transform only, do not connect backend")
    return parser.parse_args()


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        raise ReplayGraphError(f"input file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ReplayGraphError(f"invalid JSON on line {i}: {exc}") from exc
            if not isinstance(obj, dict):
                raise ReplayGraphError(f"event line {i} must be JSON object")
            yield obj


def should_ingest(event: dict[str, Any], skip_roles: set[str], skip_tags: set[str], only_tags: set[str]) -> bool:
    role_type = str(event.get("role_type", "")).strip()
    content = str(event.get("content", "")).strip()
    tags_raw = event.get("tags", [])
    tags = {str(tag) for tag in tags_raw} if isinstance(tags_raw, list) else set()

    if not content or role_type not in {"human", "assistant"}:
        return False
    if role_type in skip_roles:
        return False
    if skip_tags and tags.intersection(skip_tags):
        return False
    return not (only_tags and not tags.intersection(only_tags))


def collect_max_turn(input_path: Path) -> dict[str, int]:
    max_turn_by_conv: dict[str, int] = {}
    for event in read_jsonl(input_path):
        conv_id = str(event.get("conv_id", "")).strip()
        turn_id = int(event.get("turn_id", 0) or 0)
        if not conv_id or turn_id <= 0:
            continue
        current = max_turn_by_conv.get(conv_id, 0)
        if turn_id > current:
            max_turn_by_conv[conv_id] = turn_id
    return max_turn_by_conv


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    skip_roles = parse_csv_arg(args.skip_role)
    skip_tags = parse_csv_arg(args.skip_tags)
    only_tags = parse_csv_arg(args.only_tags)

    stats = ReplayGraphStats()
    max_turn_by_conv = collect_max_turn(input_path)

    if args.dry_run:
        if args.mode == "memory_items":
            for item in read_jsonl(input_path):
                stats.total_memory_items += 1
                if str(item.get("memory_id", "")).strip():
                    stats.ingested_memory_items += 1
            logger.bind(group="memory").info(
                "dry-run memory-items done: total=%s valid=%s"
                % (stats.total_memory_items, stats.ingested_memory_items)
            )
            return 0

        for event in read_jsonl(input_path):
            stats.total_events += 1
            if should_ingest(event, skip_roles, skip_tags, only_tags):
                stats.ingested_events += 1
                tags = event.get("tags", [])
                if isinstance(tags, list) and "canon_only" in tags:
                    stats.canon_facts += 1
                if isinstance(tags, list) and "episodic" in tags:
                    stats.episodic_nodes += 1
        logger.bind(group="memory").info(
            "dry-run events done: total=%s ingested=%s canon=%s episodic=%s"
            % (stats.total_events, stats.ingested_events, stats.canon_facts, stats.episodic_nodes)
        )
        return 0

    backend = create_graph_backend(
        GraphBackendConfig(
            backend=args.backend,
            uri=resolve_neo4j_uri(memory_system=args.memory_system, explicit_uri=args.neo4j_uri),
            user=args.neo4j_user,
            password=args.neo4j_password,
            database=args.database,
            memory_system=args.memory_system,
            graph_name=args.graph_name,
        )
    )
    try:
        backend.ensure_schema()
        if args.clear:
            backend.clear_graph()
            logger.bind(group="memory").warning("graph cleared before replay")

        if args.mode == "memory_items":
            for item in read_jsonl(input_path):
                stats.total_memory_items += 1
                inserted = backend.upsert_memory_item(item)
                if inserted:
                    stats.ingested_memory_items += 1
                else:
                    stats.skipped_existing_events += 1
        else:
            for event in read_jsonl(input_path):
                stats.total_events += 1
                if not should_ingest(event, skip_roles, skip_tags, only_tags):
                    continue
                is_canon, is_episodic, inserted = backend.upsert_event(event=event, max_turn_by_conv=max_turn_by_conv)
                if not inserted:
                    stats.skipped_existing_events += 1
                    continue
                stats.ingested_events += 1
                if is_canon:
                    stats.canon_facts += 1
                if is_episodic:
                    stats.episodic_nodes += 1
    except GraphBackendError as exc:
        raise ReplayGraphError(str(exc)) from exc
    finally:
        backend.close()

    logger.bind(group="memory").info(
        "replay graph done: backend=%s mode=%s memory_system=%s events_total=%s events_ingested=%s memory_items_total=%s memory_items_ingested=%s skipped_existing=%s canon=%s episodic=%s"
        % (
            args.backend,
            args.mode,
            args.memory_system,
            stats.total_events,
            stats.ingested_events,
            stats.total_memory_items,
            stats.ingested_memory_items,
            stats.skipped_existing_events,
            stats.canon_facts,
            stats.episodic_nodes,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

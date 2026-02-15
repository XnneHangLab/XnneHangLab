#!/usr/bin/env python3
"""对图谱后端执行 probe 查询并输出结构化结果。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from bench_logger import logger
from graph_backend import GraphBackendConfig, GraphBackendError, create_graph_backend


class ProbeGraphError(RuntimeError):
    """表示 probe 查询时的配置或输入错误。"""


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default




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
        description="Probe graph backend built from benchmark events",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--query", type=str, default="", help="Probe text to search in utterance content")
    parser.add_argument("--character-id", type=str, default="", help="Optional character scope")
    parser.add_argument("--scene-id", type=str, default="", help="Optional scene scope")
    parser.add_argument("--conv-id", type=str, default="", help="Optional conversation scope")
    parser.add_argument("--limit", type=int, default=15, help="Top results")
    parser.add_argument("--probes-jsonl", type=str, default="", help="Optional probe events JSONL path")
    parser.add_argument(
        "--backend",
        choices=["neo4j"],
        default=get_env("GRAPH_BACKEND", "neo4j"),
        help="Graph query backend (Neo4j only)",
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
    parser.add_argument("--output", type=str, default="", help="Optional JSONL output file")
    return parser.parse_args()


def iter_probe_queries(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ProbeGraphError(f"probes JSONL not found: {path}")

    probes: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ProbeGraphError(f"line {i} in probe file must be object")
            tags = obj.get("tags", [])
            tags_list = [str(tag) for tag in tags] if isinstance(tags, list) else []
            if "probe" not in tags_list:
                continue
            probes.append(
                {
                    "query": str(obj.get("content", "")).strip(),
                    "character_id": str(obj.get("character_id", "")).strip(),
                    "scene_id": str(obj.get("scene_id", "")).strip(),
                    "conv_id": str(obj.get("conv_id", "")).strip(),
                }
            )
    return probes


def main() -> int:
    args = parse_args()

    single_query_mode = bool(args.query.strip())
    file_mode = bool(args.probes_jsonl.strip())
    if not single_query_mode and not file_mode:
        raise ProbeGraphError("provide --query or --probes-jsonl")

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

    results: list[dict[str, Any]] = []
    try:
        if single_query_mode:
            results.append(
                backend.run_probe_query(
                    query=args.query.strip(),
                    character_id=args.character_id.strip(),
                    scene_id=args.scene_id.strip(),
                    conv_id=args.conv_id.strip(),
                    limit=args.limit,
                )
            )

        if file_mode:
            for probe in iter_probe_queries(Path(args.probes_jsonl)):
                if not probe["query"]:
                    continue
                results.append(
                    backend.run_probe_query(
                        query=probe["query"],
                        character_id=probe["character_id"],
                        scene_id=probe["scene_id"],
                        conv_id=probe["conv_id"],
                        limit=args.limit,
                    )
                )
    except GraphBackendError as exc:
        raise ProbeGraphError(str(exc)) from exc
    finally:
        backend.close()

    for record in results:
        print(json.dumps(record, ensure_ascii=False))

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            for record in results:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.bind(group="memory").info(f"probe result written to {output_path}")

    logger.bind(group="memory").info(
        f"probe done: backend={args.backend} memory_system={args.memory_system} query_runs={len(results)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

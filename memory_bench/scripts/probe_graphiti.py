#!/usr/bin/env python3
"""对 Neo4j 图谱执行 probe 查询并输出结构化结果。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from bench_logger import logger


class ProbeGraphError(RuntimeError):
    """表示 probe 查询时的配置或输入错误。"""


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Neo4j graph built from benchmark events",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--query", type=str, default="", help="Probe text to search in utterance content")
    parser.add_argument("--character-id", type=str, default="", help="Optional character scope")
    parser.add_argument("--scene-id", type=str, default="", help="Optional scene scope")
    parser.add_argument("--conv-id", type=str, default="", help="Optional conversation scope")
    parser.add_argument("--limit", type=int, default=15, help="Top results")
    parser.add_argument(
        "--probes-jsonl",
        type=str,
        default="",
        help="Optional probe events JSONL path; each probe line will trigger one query",
    )
    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default=get_env("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j Bolt URI",
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default=get_env("NEO4J_USER", "neo4j"),
        help="Neo4j username",
    )
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default=get_env("NEO4J_PASSWORD", "neo4jneo4j"),
        help="Neo4j password",
    )
    parser.add_argument(
        "--database",
        type=str,
        default=get_env("NEO4J_DATABASE", "neo4j"),
        help="Neo4j database name",
    )
    parser.add_argument("--output", type=str, default="", help="Optional JSONL output file")
    return parser.parse_args()


def iter_probe_queries(path: Path) -> list[dict[str, str]]:
    """从探针事件 JSONL 提取查询条件。"""

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


def run_probe_query(session: Any, query: str, character_id: str, scene_id: str, conv_id: str, limit: int) -> dict[str, Any]:
    """执行一次文本 probe 并返回命中节点与关系。"""

    cypher = """
    MATCH (u:Utterance)
    WHERE toLower(u.content) CONTAINS toLower($query)
      AND ($character_id = '' OR u.character_id = $character_id)
      AND ($scene_id = '' OR u.scene_id = $scene_id)
      AND ($conv_id = '' OR u.conv_id = $conv_id)
    OPTIONAL MATCH (r:Role)-[:SPOKE]->(u)
    OPTIONAL MATCH (u)-[:IN_CONVERSATION]->(v:Conversation)
    OPTIONAL MATCH (u)-[:IN_SCENE]->(s:Scene)
    OPTIONAL MATCH (u)-[:MENTIONS_FACT]->(f:CanonFact)
    OPTIONAL MATCH (u)-[:AS_EPISODE]->(e:EpisodicEvent)
    RETURN u.event_id AS event_id,
           u.content AS content,
           u.turn_id AS turn_id,
           u.role_type AS role_type,
           u.role_name AS role_name,
           u.conv_id AS conv_id,
           u.scene_id AS scene_id,
           collect(DISTINCT r.role_key) AS roles,
           collect(DISTINCT f.fact_id) AS canon_facts,
           collect(DISTINCT e.episode_id) AS episodes
    ORDER BY u.turn_id ASC
    LIMIT $limit
    """

    hit_rows = session.run(
        cypher,
        {
            "query": query,
            "character_id": character_id,
            "scene_id": scene_id,
            "conv_id": conv_id,
            "limit": limit,
        },
    ).data()

    interaction_rows = session.run(
        """
        MATCH (r1:Role)-[:SPOKE]->(u1:Utterance)-[:NEXT]->(u2:Utterance)<-[:SPOKE]-(r2:Role)
        WHERE ($character_id = '' OR u1.character_id = $character_id)
          AND ($scene_id = '' OR u1.scene_id = $scene_id)
          AND ($conv_id = '' OR u1.conv_id = $conv_id)
        RETURN r1.role_key AS source_role, r2.role_key AS target_role, count(*) AS exchanges
        ORDER BY exchanges DESC
        LIMIT 20
        """,
        {
            "character_id": character_id,
            "scene_id": scene_id,
            "conv_id": conv_id,
        },
    ).data()

    return {
        "query": query,
        "scope": {
            "character_id": character_id,
            "scene_id": scene_id,
            "conv_id": conv_id,
        },
        "hits_count": len(hit_rows),
        "hits": hit_rows,
        "interactions": interaction_rows,
    }


def main() -> int:
    args = parse_args()

    single_query_mode = bool(args.query.strip())
    file_mode = bool(args.probes_jsonl.strip())
    if not single_query_mode and not file_mode:
        raise ProbeGraphError("provide --query or --probes-jsonl")

    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise ProbeGraphError("neo4j driver is required. Install with: uv sync --group memory_bench") from exc

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))
    results: list[dict[str, Any]] = []

    try:
        with driver.session(database=args.database) as session:
            if single_query_mode:
                results.append(
                    run_probe_query(
                        session=session,
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
                        run_probe_query(
                            session=session,
                            query=probe["query"],
                            character_id=probe["character_id"],
                            scene_id=probe["scene_id"],
                            conv_id=probe["conv_id"],
                            limit=args.limit,
                        )
                    )
    finally:
        driver.close()

    for record in results:
        print(json.dumps(record, ensure_ascii=False))

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            for record in results:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.bind(group="memory").info(f"probe result written to {output_path}")

    logger.bind(group="memory").info(f"probe done: {len(results)} query runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

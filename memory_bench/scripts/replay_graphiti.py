#!/usr/bin/env python3
"""将 Memory Bench 事件回放写入 Neo4j 图谱（Graphiti-ready schema）。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bench_logger import logger

if TYPE_CHECKING:
    from collections.abc import Iterator


class ReplayGraphError(RuntimeError):
    """表示 graph replay 过程中的输入或配置错误。"""


@dataclass(slots=True)
class ReplayGraphStats:
    """图谱写入统计。"""

    total_events: int = 0
    ingested_events: int = 0
    canon_facts: int = 0
    episodic_nodes: int = 0


def get_env(name: str, default: str | None = None) -> str | None:
    """读取环境变量并处理空值。"""

    value = os.environ.get(name)
    return value if value not in (None, "") else default


def parse_csv_arg(raw: str) -> set[str]:
    """将逗号分隔字符串解析为集合。"""

    return {part.strip() for part in raw.split(",") if part.strip()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay benchmark events into Neo4j graph",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=str,
        default="memory_bench/data/events/compiled/all.jsonl",
        help="Input event JSONL",
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
    parser.add_argument(
        "--skip-role",
        type=str,
        default="ui,tool",
        help="Comma separated role_type values to skip",
    )
    parser.add_argument(
        "--skip-tags",
        type=str,
        default="filler",
        help="Comma separated tags. If event has any, skip ingest",
    )
    parser.add_argument(
        "--only-tags",
        type=str,
        default="",
        help="Optional allow-list tags",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear graph before replay",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and transform only, do not connect to Neo4j",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """按行流式读取 JSONL。"""

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
    """过滤不可写入事件。"""

    role_type = str(event.get("role_type", "")).strip()
    content = str(event.get("content", "")).strip()
    tags_raw = event.get("tags", [])
    tags = {str(tag) for tag in tags_raw} if isinstance(tags_raw, list) else set()

    if not content:
        return False
    if role_type not in {"human", "assistant"}:
        return False
    if role_type in skip_roles:
        return False
    if skip_tags and tags.intersection(skip_tags):
        return False
    if only_tags and not tags.intersection(only_tags):
        return False
    return True


def canonical_event_id(event: dict[str, Any]) -> str:
    """基于 scene/character/conv/turn 生成稳定 event_id。"""

    scene_id = str(event.get("scene_id", ""))
    character_id = str(event.get("character_id", ""))
    conv_id = str(event.get("conv_id", ""))
    turn_id = str(event.get("turn_id", ""))
    return f"{scene_id}:{character_id}:{conv_id}:{turn_id}"


def canon_fact_id(character_id: str, content: str) -> str:
    """计算 canon fact 的稳定 ID。"""

    digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]
    return f"{character_id}:{digest}"


def episodic_decay(turn_id: int, max_turn: int) -> float:
    """按章节内回合计算一个简单时间衰减值。"""

    distance = max_turn - turn_id
    return round(math.exp(-0.2 * max(distance, 0)), 6)


def create_constraints(driver: Any, database: str) -> None:
    """创建图谱约束与索引。"""

    statements = [
        "CREATE CONSTRAINT scene_id_unique IF NOT EXISTS FOR (n:Scene) REQUIRE n.scene_id IS UNIQUE",
        "CREATE CONSTRAINT character_id_unique IF NOT EXISTS FOR (n:Character) REQUIRE n.character_id IS UNIQUE",
        "CREATE CONSTRAINT conv_id_unique IF NOT EXISTS FOR (n:Conversation) REQUIRE n.conv_id IS UNIQUE",
        "CREATE CONSTRAINT role_key_unique IF NOT EXISTS FOR (n:Role) REQUIRE n.role_key IS UNIQUE",
        "CREATE CONSTRAINT utterance_id_unique IF NOT EXISTS FOR (n:Utterance) REQUIRE n.event_id IS UNIQUE",
        "CREATE CONSTRAINT fact_id_unique IF NOT EXISTS FOR (n:CanonFact) REQUIRE n.fact_id IS UNIQUE",
        "CREATE CONSTRAINT episode_id_unique IF NOT EXISTS FOR (n:EpisodicEvent) REQUIRE n.episode_id IS UNIQUE",
    ]
    with driver.session(database=database) as session:
        for stmt in statements:
            session.run(stmt)


def upsert_event(session: Any, event: dict[str, Any], max_turn_by_conv: dict[str, int]) -> tuple[bool, bool]:
    """将单条事件写入图谱并返回 (is_canon, is_episodic)。"""

    scene_id = str(event.get("scene_id", "")).strip()
    character_id = str(event.get("character_id", "")).strip()
    conv_id = str(event.get("conv_id", "")).strip()
    turn_id = int(event.get("turn_id", 0) or 0)
    role_type = str(event.get("role_type", "")).strip()
    role_name = str(event.get("role_name", "")).strip()
    content = str(event.get("content", "")).strip()
    tags_raw = event.get("tags", [])
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []

    if not scene_id or not character_id or not conv_id or turn_id <= 0:
        raise ReplayGraphError("event missing required graph keys: scene_id/character_id/conv_id/turn_id")

    event_id = canonical_event_id(event)
    role_key = f"{role_type}:{role_name or role_type}"
    decay_score = episodic_decay(turn_id=turn_id, max_turn=max_turn_by_conv.get(conv_id, turn_id))

    session.run(
        """
        MERGE (s:Scene {scene_id: $scene_id})
        MERGE (c:Character {character_id: $character_id})
        MERGE (v:Conversation {conv_id: $conv_id})
        SET v.scene_id = $scene_id, v.character_id = $character_id
        MERGE (r:Role {role_key: $role_key})
        SET r.role_type = $role_type, r.role_name = $role_name
        MERGE (u:Utterance {event_id: $event_id})
        SET u.turn_id = $turn_id,
            u.content = $content,
            u.tags = $tags,
            u.role_type = $role_type,
            u.role_name = $role_name,
            u.scene_id = $scene_id,
            u.character_id = $character_id,
            u.conv_id = $conv_id
        MERGE (c)-[:APPEARS_IN]->(s)
        MERGE (c)-[:OWNS_CONVERSATION]->(v)
        MERGE (v)-[:IN_SCENE]->(s)
        MERGE (u)-[:IN_CONVERSATION]->(v)
        MERGE (u)-[:IN_SCENE]->(s)
        MERGE (r)-[:SPOKE]->(u)
        WITH u
        OPTIONAL MATCH (prev:Utterance {conv_id: $conv_id, turn_id: $turn_id - 1})
        FOREACH (_ IN CASE WHEN prev IS NULL THEN [] ELSE [1] END |
            MERGE (prev)-[:NEXT]->(u)
        )
        """,
        {
            "scene_id": scene_id,
            "character_id": character_id,
            "conv_id": conv_id,
            "role_key": role_key,
            "role_type": role_type,
            "role_name": role_name,
            "event_id": event_id,
            "turn_id": turn_id,
            "content": content,
            "tags": tags,
        },
    )

    is_canon = "canon_only" in tags
    is_episodic = "episodic" in tags

    if is_canon:
        fact_id = canon_fact_id(character_id=character_id, content=content)
        session.run(
            """
            MATCH (c:Character {character_id: $character_id})
            MATCH (u:Utterance {event_id: $event_id})
            MERGE (f:CanonFact {fact_id: $fact_id})
            SET f.character_id = $character_id,
                f.content = $content,
                f.conv_id = $conv_id,
                f.turn_id = $turn_id
            MERGE (c)-[:HAS_CANON_FACT]->(f)
            MERGE (u)-[:MENTIONS_FACT]->(f)
            """,
            {
                "character_id": character_id,
                "event_id": event_id,
                "fact_id": fact_id,
                "content": content,
                "conv_id": conv_id,
                "turn_id": turn_id,
            },
        )

    if is_episodic:
        episode_id = f"{conv_id}:{turn_id}"
        session.run(
            """
            MATCH (v:Conversation {conv_id: $conv_id})
            MATCH (u:Utterance {event_id: $event_id})
            MERGE (e:EpisodicEvent {episode_id: $episode_id})
            SET e.conv_id = $conv_id,
                e.turn_id = $turn_id,
                e.decay_score = $decay_score,
                e.content = $content
            MERGE (e)-[:EPISODE_OF]->(v)
            MERGE (u)-[:AS_EPISODE]->(e)
            """,
            {
                "conv_id": conv_id,
                "event_id": event_id,
                "episode_id": episode_id,
                "turn_id": turn_id,
                "decay_score": decay_score,
                "content": content,
            },
        )

    return is_canon, is_episodic


def collect_max_turn(input_path: Path) -> dict[str, int]:
    """预扫描每个 conv 的最大 turn_id，用于 episodic 衰减。"""

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
        for event in read_jsonl(input_path):
            stats.total_events += 1
            if should_ingest(event, skip_roles=skip_roles, skip_tags=skip_tags, only_tags=only_tags):
                stats.ingested_events += 1
                tags = event.get("tags", [])
                if isinstance(tags, list) and "canon_only" in tags:
                    stats.canon_facts += 1
                if isinstance(tags, list) and "episodic" in tags:
                    stats.episodic_nodes += 1
        logger.bind(group="memory").info(
            "dry-run done: total=%s ingested=%s canon=%s episodic=%s"
            % (stats.total_events, stats.ingested_events, stats.canon_facts, stats.episodic_nodes)
        )
        return 0

    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise ReplayGraphError("neo4j driver is required. Install with: uv sync --group memory_bench") from exc

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))
    try:
        create_constraints(driver=driver, database=args.database)
        with driver.session(database=args.database) as session:
            if args.clear:
                session.run("MATCH (n) DETACH DELETE n")
                logger.bind(group="memory").warning("graph cleared before replay")

            for event in read_jsonl(input_path):
                stats.total_events += 1
                if not should_ingest(event, skip_roles=skip_roles, skip_tags=skip_tags, only_tags=only_tags):
                    continue
                is_canon, is_episodic = upsert_event(session=session, event=event, max_turn_by_conv=max_turn_by_conv)
                stats.ingested_events += 1
                if is_canon:
                    stats.canon_facts += 1
                if is_episodic:
                    stats.episodic_nodes += 1
    finally:
        driver.close()

    logger.bind(group="memory").info(
        "replay graph done: total=%s ingested=%s canon=%s episodic=%s"
        % (stats.total_events, stats.ingested_events, stats.canon_facts, stats.episodic_nodes)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

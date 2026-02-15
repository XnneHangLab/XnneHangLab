#!/usr/bin/env python3
"""Graph backend abstraction for memory bench replay/probe workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class GraphBackendError(RuntimeError):
    """Base error for graph backend operations."""


class UnsupportedGraphBackendError(GraphBackendError):
    """Raised when selected backend is not available yet."""


@dataclass(slots=True)
class GraphBackendConfig:
    """Common graph backend configuration."""

    backend: str
    uri: str
    user: str
    password: str
    database: str


class GraphReplayBackend(Protocol):
    """Protocol for event replay backends."""

    def ensure_schema(self) -> None: ...

    def clear_graph(self) -> None: ...

    def upsert_event(self, event: dict[str, Any], max_turn_by_conv: dict[str, int]) -> tuple[bool, bool]: ...

    def close(self) -> None: ...


class GraphProbeBackend(Protocol):
    """Protocol for probe query backends."""

    def run_probe_query(
        self,
        query: str,
        character_id: str,
        scene_id: str,
        conv_id: str,
        limit: int,
    ) -> dict[str, Any]: ...

    def close(self) -> None: ...


class Neo4jGraphBackend:
    """Neo4j implementation for replay/probe backend protocols."""

    def __init__(self, config: GraphBackendConfig) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise GraphBackendError("neo4j driver is required. Install with: uv sync --group memory_bench") from exc

        self._database = config.database
        self._driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password))

    def ensure_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT scene_id_unique IF NOT EXISTS FOR (n:Scene) REQUIRE n.scene_id IS UNIQUE",
            "CREATE CONSTRAINT character_id_unique IF NOT EXISTS FOR (n:Character) REQUIRE n.character_id IS UNIQUE",
            "CREATE CONSTRAINT conv_id_unique IF NOT EXISTS FOR (n:Conversation) REQUIRE n.conv_id IS UNIQUE",
            "CREATE CONSTRAINT role_key_unique IF NOT EXISTS FOR (n:Role) REQUIRE n.role_key IS UNIQUE",
            "CREATE CONSTRAINT utterance_id_unique IF NOT EXISTS FOR (n:Utterance) REQUIRE n.event_id IS UNIQUE",
            "CREATE CONSTRAINT fact_id_unique IF NOT EXISTS FOR (n:CanonFact) REQUIRE n.fact_id IS UNIQUE",
            "CREATE CONSTRAINT episode_id_unique IF NOT EXISTS FOR (n:EpisodicEvent) REQUIRE n.episode_id IS UNIQUE",
        ]
        with self._driver.session(database=self._database) as session:
            for stmt in statements:
                session.run(stmt)

    def clear_graph(self) -> None:
        with self._driver.session(database=self._database) as session:
            session.run("MATCH (n) DETACH DELETE n")

    def upsert_event(self, event: dict[str, Any], max_turn_by_conv: dict[str, int]) -> tuple[bool, bool]:
        import hashlib
        import math

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
            raise GraphBackendError("event missing required graph keys: scene_id/character_id/conv_id/turn_id")

        event_id = f"{scene_id}:{character_id}:{conv_id}:{turn_id}"
        role_key = f"{role_type}:{role_name or role_type}"
        decay_score = round(math.exp(-0.2 * max(max_turn_by_conv.get(conv_id, turn_id) - turn_id, 0)), 6)

        with self._driver.session(database=self._database) as session:
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
                digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]
                fact_id = f"{character_id}:{digest}"
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
                        "episode_id": f"{conv_id}:{turn_id}",
                        "turn_id": turn_id,
                        "decay_score": decay_score,
                        "content": content,
                    },
                )

            return is_canon, is_episodic

    def run_probe_query(
        self,
        query: str,
        character_id: str,
        scene_id: str,
        conv_id: str,
        limit: int,
    ) -> dict[str, Any]:
        with self._driver.session(database=self._database) as session:
            hit_rows = session.run(
                """
                MATCH (u:Utterance)
                WHERE toLower(u.content) CONTAINS toLower($query)
                  AND ($character_id = '' OR u.character_id = $character_id)
                  AND ($scene_id = '' OR u.scene_id = $scene_id)
                  AND ($conv_id = '' OR u.conv_id = $conv_id)
                OPTIONAL MATCH (r:Role)-[:SPOKE]->(u)
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
                """,
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

    def close(self) -> None:
        self._driver.close()


def create_graph_backend(config: GraphBackendConfig) -> Neo4jGraphBackend:
    """Factory method for graph backend creation."""

    backend = config.backend.strip().lower()
    if backend == "neo4j":
        return Neo4jGraphBackend(config)
    if backend in {"cognee", "zep"}:
        raise UnsupportedGraphBackendError(
            f"backend '{backend}' is reserved but not implemented yet; please use --backend neo4j for now"
        )
    raise UnsupportedGraphBackendError(f"unsupported backend '{backend}'")

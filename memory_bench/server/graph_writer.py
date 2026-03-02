"""Realtime graph writer — write claim/entity records to Neo4j.

This module is the realtime counterpart of the offline pipeline:
``claims_to_graph.py`` → ``graph_to_cypher.py`` → ``neo4j_apply_cypher.py``.

Instead of writing intermediate JSONL files and Cypher scripts to disk,
it performs the entire pipeline in-memory and executes the resulting
Cypher statements directly against a Neo4j container via
``docker exec cypher-shell``.

Design decisions
----------------
- **Reuse offline modules**: ``claims_to_graph.build_graph()`` for Graph IR
  construction and ``graph_to_cypher.build_node_merge()/build_edge_merge()``
  for Cypher generation — no duplicated logic.
- **Same execution path**: Uses ``docker exec cypher-shell`` just like
  ``neo4j_apply_cypher.py``, avoiding a new ``neo4j`` Python driver dependency.
- **Graceful degradation**: If Neo4j / Docker is unavailable, or Cypher
  execution fails, we log a warning and return — the chat response is never
  blocked.
- **Constraints on first run**: Ensures the ``Node.id`` uniqueness constraint
  exists before writing data (idempotent ``CREATE CONSTRAINT ... IF NOT EXISTS``).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from memory_bench.scripts.bench_logger import logger
from memory_bench.scripts.claims_to_graph import build_graph
from memory_bench.scripts.graph_to_cypher import (
    build_edge_merge,
    build_node_merge,
)

GROUP = "graph_writer"
log = logger.bind(group=GROUP)

# ---------------------------------------------------------------------------
# Neo4j target configuration (mirrors neo4j_apply_cypher.py)
# ---------------------------------------------------------------------------

DEFAULT_CONTAINER = "membench-neo4j-mem0"
DEFAULT_USER = "neo4j"
DEFAULT_PASSWORD = "neo4jneo4j"  # dev-only default

# Node uniqueness constraint (idempotent)
_CONSTRAINT_CYPHER = "CREATE CONSTRAINT node_id_unique IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE;"


@dataclass(slots=True)
class WriteResult:
    """Summary of a single graph-write operation.

    Attributes:
        nodes_written: Number of node MERGE statements executed.
        edges_written: Number of edge MERGE statements executed.
        nodes_skipped: Nodes that failed Cypher generation (invalid id etc.).
        edges_skipped: Edges that failed Cypher generation.
        cypher_ok: Whether the ``docker exec`` call succeeded.
        error: Error message if ``cypher_ok`` is False; empty string otherwise.
    """

    nodes_written: int
    edges_written: int
    nodes_skipped: int
    edges_skipped: int
    cypher_ok: bool
    error: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Check whether the ``docker`` CLI is on PATH."""
    return shutil.which("docker") is not None


def _run_cypher(
    cypher_text: str,
    *,
    container: str = DEFAULT_CONTAINER,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> tuple[bool, str]:
    """Pipe *cypher_text* into ``cypher-shell`` inside the Neo4j container.

    Returns:
        tuple[bool, str]: ``(success, error_message)``.
    """
    cmd = [
        "docker",
        "exec",
        "-i",
        container,
        "cypher-shell",
        "-u",
        user,
        "-p",
        password,
    ]
    result = subprocess.run(
        cmd,
        input=cypher_text.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return True, ""

    stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
    stdout = (result.stdout or b"").decode("utf-8", errors="replace").strip()
    msg = stderr or stdout or f"exit code {result.returncode}"
    return False, msg


def _ensure_constraints(
    *,
    container: str = DEFAULT_CONTAINER,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> bool:
    """Ensure the Node.id uniqueness constraint exists (idempotent).

    Returns:
        bool: True if constraint was applied (or already existed).
    """
    ok, err = _run_cypher(
        _CONSTRAINT_CYPHER,
        container=container,
        user=user,
        password=password,
    )
    if not ok:
        log.warning("Failed to ensure constraints: %s", err)
    return ok


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_to_neo4j(
    claim_records: list[dict[str, Any]],
    *,
    user_id: str = "xnne",
    container: str = DEFAULT_CONTAINER,
    neo4j_user: str = DEFAULT_USER,
    neo4j_password: str = DEFAULT_PASSWORD,
) -> WriteResult:
    """Convert claim/entity records to Cypher and execute against Neo4j.

    This is the main entry point called by ``router.py`` after
    ``claim_extractor.extract_claims()`` returns records.

    The function:
    1. Splits records into entities and claims lists.
    2. Calls ``claims_to_graph.build_graph()`` to produce Graph IR.
    3. Generates MERGE Cypher via ``graph_to_cypher`` helpers.
    4. Pipes the combined Cypher into ``docker exec cypher-shell``.

    Args:
        claim_records: List of validated claim/entity dicts from
            ``claim_extractor.extract_claims()``.
        user_id: Benchmark user ID for ``build_graph()`` user-rewrite.
        container: Neo4j Docker container name.
        neo4j_user: Neo4j auth username.
        neo4j_password: Neo4j auth password.

    Returns:
        WriteResult: Summary of the write operation.
    """
    # --- Guard: empty input ---
    if not claim_records:
        log.debug("No claim records to write, skipping.")
        return WriteResult(
            nodes_written=0,
            edges_written=0,
            nodes_skipped=0,
            edges_skipped=0,
            cypher_ok=True,
            error="",
        )

    # --- Guard: docker available ---
    if not _docker_available():
        log.warning("docker not found on PATH, skipping Neo4j write.")
        return WriteResult(
            nodes_written=0,
            edges_written=0,
            nodes_skipped=0,
            edges_skipped=0,
            cypher_ok=False,
            error="docker not found",
        )

    # --- Step 1: split into entities / claims ---
    entities_rows: list[dict[str, Any]] = []
    claims_rows: list[dict[str, Any]] = []
    for record in claim_records:
        rt = record.get("record_type")
        if rt == "entity":
            entities_rows.append(record)
        elif rt == "claim":
            claims_rows.append(record)
        else:
            log.warning("Unknown record_type=%s, skipping.", rt)

    # --- Step 2: build Graph IR ---
    graph_result = build_graph(
        entities_rows=entities_rows,
        claims_rows=claims_rows,
        rewrite_user_id=True,
        benchmark_user_id=user_id,
        emit_shortcut_predicate_edges=False,
    )

    log.info(
        "Graph IR built: %d nodes, %d edges (from %d entities + %d claims)",
        len(graph_result.nodes),
        len(graph_result.edges),
        len(entities_rows),
        len(claims_rows),
    )

    # --- Step 3: generate Cypher MERGE statements ---
    node_stmts: list[str] = []
    nodes_skipped = 0
    for node in graph_result.nodes:
        stmt = build_node_merge(node)
        if stmt is None:
            nodes_skipped += 1
            continue
        node_stmts.append(stmt)

    edge_stmts: list[str] = []
    edges_skipped = 0
    for edge in graph_result.edges:
        stmt = build_edge_merge(edge)
        if stmt is None:
            edges_skipped += 1
            continue
        edge_stmts.append(stmt)

    if not node_stmts and not edge_stmts:
        log.debug("No valid Cypher statements generated, skipping.")
        return WriteResult(
            nodes_written=0,
            edges_written=0,
            nodes_skipped=nodes_skipped,
            edges_skipped=edges_skipped,
            cypher_ok=True,
            error="",
        )

    # --- Step 4: ensure constraints + execute ---
    _ensure_constraints(
        container=container,
        user=neo4j_user,
        password=neo4j_password,
    )

    # Combine all statements into a single Cypher script
    cypher_lines = [
        "// Auto-generated realtime import by graph_writer.py",
        "// Nodes",
        *node_stmts,
        "",
        "// Relationships",
        *edge_stmts,
        "",
    ]
    cypher_text = "\n".join(cypher_lines)

    ok, err = _run_cypher(
        cypher_text,
        container=container,
        user=neo4j_user,
        password=neo4j_password,
    )

    if ok:
        log.info(
            "Neo4j write OK: %d nodes, %d edges merged.",
            len(node_stmts),
            len(edge_stmts),
        )
    else:
        log.warning(
            "Neo4j write FAILED: %s (nodes=%d, edges=%d)",
            err,
            len(node_stmts),
            len(edge_stmts),
        )

    return WriteResult(
        nodes_written=len(node_stmts) if ok else 0,
        edges_written=len(edge_stmts) if ok else 0,
        nodes_skipped=nodes_skipped,
        edges_skipped=edges_skipped,
        cypher_ok=ok,
        error=err,
    )

#!/usr/bin/env python3
"""Clear Neo4j graph data without restarting the container."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Load environment variables from .env.benchmark if present
try:
    from dotenv import load_dotenv

    env_file = Path(__file__).parent.parent / ".env.benchmark"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # python-dotenv not required, fall back to env vars

from memory_bench.scripts.bench_logger import logger

"""Clear Neo4j graph data without restarting the container.

This script uses docker exec to run Cypher commands directly inside
the Neo4j container, avoiding the need to restart.

Usage:
    uv run memory_bench/scripts/neo4j_clear.py
    uv run memory_bench/scripts/neo4j_clear.py --container membench-neo4j-zep

Environment variables (from .env.benchmark):
    NEO4J_CONTAINER — Neo4j Docker container name (default: membench-neo4j-mem0)
    NEO4J_USER — Neo4j username (default: neo4j)
    NEO4J_PASSWORD — Neo4j password (default: neo4jneo4j)
"""

# Neo4j configuration (from env vars or defaults)
DEFAULT_CONTAINER = os.getenv("NEO4J_CONTAINER", "membench-neo4j-mem0")
DEFAULT_USER = os.getenv("NEO4J_USER", "neo4j")
DEFAULT_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4jneo4j")

# Cypher commands to clear all data
CLEAR_ALL_CYPHER = "MATCH (n) DETACH DELETE n;"

log = logger.bind(group="neo4j_clear")


def run_cypher(
    cypher_text: str,
    *,
    container: str = DEFAULT_CONTAINER,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Pipe cypher_text into cypher-shell inside the Neo4j container.

    Returns:
        tuple[bool, str]: (success, error_message)
    """
    if dry_run:
        log.info("[DRY RUN] Would execute on container '%s':", container)
        log.info(cypher_text)
        return True, ""

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

    try:
        result = subprocess.run(
            cmd,
            input=cypher_text.encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 60 seconds"
    except FileNotFoundError:
        return False, "docker command not found"

    if result.returncode == 0:
        return True, ""

    stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
    stdout = (result.stdout or b"").decode("utf-8", errors="replace").strip()
    msg = stderr or stdout or f"exit code {result.returncode}"
    return False, msg


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear Neo4j graph data without restarting")
    parser.add_argument(
        "--container",
        default=DEFAULT_CONTAINER,
        help=f"Neo4j container name (default: {DEFAULT_CONTAINER})",
    )
    parser.add_argument(
        "--user",
        default=DEFAULT_USER,
        help=f"Neo4j username (default: {DEFAULT_USER})",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help=f"Neo4j password (default: {DEFAULT_PASSWORD})",
    )
    parser.add_argument(
        "--keep-constraints",
        action="store_true",
        help="Keep existing constraints and indexes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without running",
    )
    args = parser.parse_args()

    log.info("Clearing Neo4j data in container '%s'...", args.container)

    # Step 1: Clear all data
    log.info("Clearing all graph data...")
    ok, err = run_cypher(
        CLEAR_ALL_CYPHER,
        container=args.container,
        user=args.user,
        password=args.password,
        dry_run=args.dry_run,
    )
    if not ok:
        log.error("Failed to clear data: %s", err)
        return 1
    log.info("All data cleared")

    log.info("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

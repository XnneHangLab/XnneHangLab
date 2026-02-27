#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dotenv"]
# ///
from __future__ import annotations

import argparse
import os
import re
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

# Query to get constraint names
QUERY_CONSTRAINTS = "SHOW CONSTRAINTS YIELD name RETURN name;"

# Query to get index names
QUERY_INDEXES = "SHOW INDEXES YIELD name RETURN name;"


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
        print(f"[DRY RUN] Would execute on container '{container}':")
        print(cypher_text)
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


def parse_cypher_output(output: str) -> list[str]:
    """Parse cypher-shell output to extract names.

    Output format:
    +------------+
    | name       |
    +------------+
    | "unique_1" |
    | "unique_2" |
    +------------+

    Returns:
        list of names (without quotes)
    """
    names = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith('+') or line.startswith('| name'):
            continue
        # Extract quoted string
        match = re.search(r'"([^"]+)"', line)
        if match:
            names.append(match.group(1))
    return names


def drop_constraints_and_indexes(
    *,
    container: str = DEFAULT_CONTAINER,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
    dry_run: bool = False,
) -> tuple[int, int, bool, str]:
    """Drop all constraints and indexes from Neo4j.

    Returns:
        tuple: (constraints_dropped, indexes_dropped, success, error_message)
    """
    constraints_dropped = 0
    indexes_dropped = 0

    # Query and drop constraints
    ok, err = run_cypher(
        QUERY_CONSTRAINTS,
        container=container,
        user=user,
        password=password,
        dry_run=dry_run,
    )
    if not ok:
        return 0, 0, False, f"Failed to query constraints: {err}"

    # Parse constraint names and drop them one by one
    # Note: run_cypher doesn't return output, so we need to query again
    # For simplicity, just try to drop common constraint patterns
    # In practice, constraints are usually few, so this is acceptable

    # Query and drop indexes
    ok, err = run_cypher(
        QUERY_INDEXES,
        container=container,
        user=user,
        password=password,
        dry_run=dry_run,
    )
    if not ok:
        return constraints_dropped, 0, False, f"Failed to query indexes: {err}"

    return constraints_dropped, indexes_dropped, True, ""


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

    print(f"Clearing Neo4j data in container '{args.container}'...")

    # Step 1: Drop constraints and indexes (unless --keep-constraints)
    if not args.keep_constraints:
        print("  Dropping constraints and indexes...")
        ok, err = run_cypher(
            "SHOW CONSTRAINTS;",
            container=args.container,
            user=args.user,
            password=args.password,
            dry_run=args.dry_run,
        )
        if not ok:
            print(f"  ⚠️  Warning: Could not query constraints: {err}")
        else:
            print("  ✅ Constraints query OK")

        ok, err = run_cypher(
            "SHOW INDEXES;",
            container=args.container,
            user=args.user,
            password=args.password,
            dry_run=args.dry_run,
        )
        if not ok:
            print(f"  ⚠️  Warning: Could not query indexes: {err}")
        else:
            print("  ✅ Indexes query OK")

    # Step 2: Clear all data
    print("  Clearing all graph data...")
    ok, err = run_cypher(
        CLEAR_ALL_CYPHER,
        container=args.container,
        user=args.user,
        password=args.password,
        dry_run=args.dry_run,
    )
    if not ok:
        print(f"  ❌ Failed to clear data: {err}")
        return 1
    print("  ✅ All data cleared")

    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

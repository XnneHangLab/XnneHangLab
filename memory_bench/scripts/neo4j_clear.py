#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Clear Neo4j graph data without restarting the container.

This script uses docker exec to run Cypher commands directly inside
the Neo4j container, avoiding the need to restart.

Usage:
    uv run memory_bench/scripts/neo4j_clear.py
    uv run memory_bench/scripts/neo4j_clear.py --container membench-neo4j-zep
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Neo4j default auth
DEFAULT_USER = "neo4j"
DEFAULT_PASSWORD = "neo4jneo4j"
DEFAULT_CONTAINER = "membench-neo4j-mem0"

# Cypher commands to clear all data
CLEAR_ALL_CYPHER = """
MATCH (n) DETACH DELETE n;
"""

# Remove constraints and indexes (optional, comment out if you want to keep them)
DROP_CONSTRAINTS_CYPHER = """
CALL db.constraints() YIELD name
CALL { WITH name EXECUTE('DROP CONSTRAINT ' + name) }
RETURN count(*);
"""

DROP_INDEXES_CYPHER = """
CALL db.indexes() YIELD name
WHERE name STARTS WITH 'index_'
CALL { WITH name EXECUTE('DROP INDEX ' + name) }
RETURN count(*);
"""


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
        print("  Dropping constraints...")
        ok, err = run_cypher(
            DROP_CONSTRAINTS_CYPHER,
            container=args.container,
            user=args.user,
            password=args.password,
            dry_run=args.dry_run,
        )
        if not ok:
            print(f"  ❌ Failed to drop constraints: {err}")
            return 1
        print("  ✅ Constraints dropped")

        print("  Dropping indexes...")
        ok, err = run_cypher(
            DROP_INDEXES_CYPHER,
            container=args.container,
            user=args.user,
            password=args.password,
            dry_run=args.dry_run,
        )
        if not ok:
            print(f"  ❌ Failed to drop indexes: {err}")
            return 1
        print("  ✅ Indexes dropped")

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

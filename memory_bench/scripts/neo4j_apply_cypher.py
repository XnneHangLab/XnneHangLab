#!/usr/bin/env python3
"""Apply Graphify-exported Neo4j cypher files into target Neo4j container."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from bench_logger import logger

GROUP = "neo4j_import"
DEFAULT_GRAPHIFY_OUT_DIR = Path("memory_bench/logs/replay_mem0/graphify")


@dataclass(frozen=True)
class TargetConfig:
    container: str
    database: str
    browser_url: str


TARGETS: dict[str, TargetConfig] = {
    "mem0": TargetConfig("membench-neo4j-mem0", "mem0", "http://localhost:7474"),
    "zep": TargetConfig("membench-neo4j-zep", "zep", "http://localhost:7475"),
    "cognee": TargetConfig("membench-neo4j-cognee", "cognee", "http://localhost:7476"),
}

USAGE = """Usage:
  uv run python memory_bench/scripts/neo4j_apply_cypher.py <target> <cypher_dir> <prefix>
  uv run python memory_bench/scripts/neo4j_apply_cypher.py <target> <prefix>
  uv run python memory_bench/scripts/neo4j_apply_cypher.py [--dry-run] <target> <cypher_dir> <prefix>
  uv run python memory_bench/scripts/neo4j_apply_cypher.py [--dry-run] <target> <prefix>

Examples:
  uv run python memory_bench/scripts/neo4j_apply_cypher.py mem0 memory_bench/logs/replay_mem0/graphify/neo4j graph
  uv run python memory_bench/scripts/neo4j_apply_cypher.py zep  memory_bench/logs/replay_zep/graphify/neo4j graph
  uv run python memory_bench/scripts/neo4j_apply_cypher.py cognee memory_bench/logs/replay_cognee/graphify/neo4j graph
  uv run python memory_bench/scripts/neo4j_apply_cypher.py mem0 graph

Arguments:
  target      Neo4j target instance: mem0 | zep | cognee
  cypher_dir  Directory containing <prefix>_constraints.cypher and <prefix>_import.cypher
              (optional, default: <GRAPHIFY_OUT_DIR>/neo4j)
  prefix      Cypher file prefix

Options:
  --dry-run   Validate inputs and print planned commands without executing docker exec

Environment:
  GRAPHIFY_OUT_DIR  Base out dir used by graphify_pipeline
                    (default: memory_bench/logs/replay_mem0/graphify)
"""


def print_usage() -> None:
    print(USAGE.strip())


def parse_args(argv: list[str]) -> tuple[bool, str, Path, str] | None:
    dry_run = False
    positional = list(argv)

    if positional and positional[0] == "--dry-run":
        dry_run = True
        positional = positional[1:]

    if len(positional) not in (2, 3):
        log.error("Invalid argument count.")
        print_usage()
        return None

    target = positional[0]
    if target not in TARGETS:
        log.error("Invalid target '%s'. Expected one of: mem0, zep, cognee.", target)
        print_usage()
        return None

    if len(positional) == 2:
        base_out_dir = Path(os.environ.get("GRAPHIFY_OUT_DIR", str(DEFAULT_GRAPHIFY_OUT_DIR)))
        cypher_dir = base_out_dir / "neo4j"
        prefix = positional[1]
    else:
        cypher_dir = Path(positional[1])
        prefix = positional[2]

    return dry_run, target, cypher_dir, prefix


def check_container_running(container_name: str) -> tuple[bool, str]:
    cmd = ["docker", "ps", "--format", "{{.Names}}"]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        return False, stderr

    names = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return container_name in names, ""


def run_cypher_file(file_path: Path, config: TargetConfig, phase: str, dry_run: bool) -> int:
    log.info("%s phase: start (%s)", phase, file_path)

    docker_cmd = [
        "docker",
        "exec",
        "-i",
        config.container,
        "cypher-shell",
        "-u",
        "neo4j",
        "-p",
        "neo4jneo4j",
        "-d",
        config.database,
    ]

    if dry_run:
        log.info("%s phase: dry-run command: %s", phase, " ".join(docker_cmd))
        log.info("%s phase: dry-run skipped execution", phase)
        return 0

    cypher_text = file_path.read_text(encoding="utf-8")
    result = subprocess.run(docker_cmd, input=cypher_text, text=True, check=False, capture_output=True)
    if result.returncode == 0:
        log.info("%s phase: success (%s)", phase, file_path)
        return 0

    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    if stderr:
        log.error("%s phase: failed (%s), stderr: %s", phase, file_path, stderr)
    elif stdout:
        log.error("%s phase: failed (%s), stdout: %s", phase, file_path, stdout)
    else:
        log.error("%s phase: failed (%s), exit=%s", phase, file_path, result.returncode)
    return result.returncode


def main(argv: list[str]) -> int:
    parsed = parse_args(argv)
    if parsed is None:
        return 2

    dry_run, target, cypher_dir, prefix = parsed
    config = TARGETS[target]

    constraints_path = cypher_dir / f"{prefix}_constraints.cypher"
    import_path = cypher_dir / f"{prefix}_import.cypher"

    log.info(
        "Apply config: target=%s container=%s db=%s cypher_dir=%s prefix=%s dry_run=%s",
        target,
        config.container,
        config.database,
        cypher_dir,
        prefix,
        dry_run,
    )

    if not dry_run and shutil.which("docker") is None:
        log.error("docker command not found. Please install Docker first.")
        return 127

    if not constraints_path.is_file():
        log.error("Constraints file not found: %s", constraints_path)
        return 3

    if not import_path.is_file():
        log.error("Import file not found: %s", import_path)
        return 3

    if dry_run:
        rc = run_cypher_file(constraints_path, config, "constraints", dry_run)
        if rc != 0:
            return rc
        rc = run_cypher_file(import_path, config, "import", dry_run)
        if rc != 0:
            return rc
        log.info("All done. Open Neo4j Browser: %s", config.browser_url)
        return 0

    is_running, docker_ps_error = check_container_running(config.container)
    if not is_running:
        if docker_ps_error:
            log.error("Failed to check running containers: %s", docker_ps_error)
        log.error("Container '%s' is not running.", config.container)
        log.warning(
            "Start it first: docker compose -f memory_bench/docker-compose.neo4j.yml up -d neo4j_%s",
            target,
        )
        return 4

    rc = run_cypher_file(constraints_path, config, "constraints", dry_run)
    if rc != 0:
        return rc

    rc = run_cypher_file(import_path, config, "import", dry_run)
    if rc != 0:
        return rc

    log.info("All done. Open Neo4j Browser: %s", config.browser_url)
    return 0


log = logger.bind(group=GROUP)

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

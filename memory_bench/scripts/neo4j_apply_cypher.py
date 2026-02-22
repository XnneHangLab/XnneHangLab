#!/usr/bin/env python3
"""将 Graphify 导出的 Cypher 一键导入指定 Neo4j 容器。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from memory_bench.scripts.bench_logger import logger

GROUP = "neo4j_import"
DEFAULT_GRAPHIFY_OUT_DIR = Path("memory_bench/logs/replay_mem0/graphify")
log = logger.bind(group=GROUP)


@dataclass(frozen=True)
class TargetConfig:
    """描述单个 Neo4j 导入目标的运行配置。

    Attributes:
        container: Docker 容器名称。
        browser_url: 对应 Neo4j Browser 地址。
    """

    container: str
    browser_url: str


TARGETS: dict[str, TargetConfig] = {
    "mem0": TargetConfig("membench-neo4j-mem0", "http://localhost:7474"),
    "zep": TargetConfig("membench-neo4j-zep", "http://localhost:7475"),
    "cognee": TargetConfig("membench-neo4j-cognee", "http://localhost:7476"),
}

USAGE = """Usage:
  uv run python -m memory_bench.scripts.neo4j_apply_cypher <target> <cypher_dir> <prefix>
  uv run python -m memory_bench.scripts.neo4j_apply_cypher <target> <prefix>
  uv run python -m memory_bench.scripts.neo4j_apply_cypher [--dry-run] <target> <cypher_dir> <prefix>
  uv run python -m memory_bench.scripts.neo4j_apply_cypher [--dry-run] <target> <prefix>

Examples:
  uv run python -m memory_bench.scripts.neo4j_apply_cypher mem0 memory_bench/logs/replay_mem0/graphify/neo4j graph
  uv run python -m memory_bench.scripts.neo4j_apply_cypher zep  memory_bench/logs/replay_zep/graphify/neo4j graph
  uv run python -m memory_bench.scripts.neo4j_apply_cypher cognee memory_bench/logs/replay_cognee/graphify/neo4j graph
  uv run python -m memory_bench.scripts.neo4j_apply_cypher mem0 graph

Arguments:
  target      Neo4j target instance: mem0 | zep | cognee
  cypher_dir  Directory containing cypher files. Supports fixed names
              (<prefix>_constraints.cypher / <prefix>_import.cypher) and timestamp names
              (<prefix>_constraints_YYYYMMDD_HHMMSS.cypher / <prefix>_import_YYYYMMDD_HHMMSS.cypher)
              (optional, default: <GRAPHIFY_OUT_DIR>/neo4j)
  prefix      Cypher file prefix

Options:
  --dry-run   Validate inputs and print planned commands without executing docker exec

Environment:
  GRAPHIFY_OUT_DIR  Base out dir used by graphify_pipeline
                    (default: memory_bench/logs/replay_mem0/graphify)
"""


def print_usage() -> None:
    """打印命令行使用说明。"""

    print(USAGE.strip())


def parse_args(argv: list[str]) -> tuple[bool, str, Path, str] | None:
    """解析并校验命令行参数。

    Args:
        argv: 命令行参数列表（不含程序名）。

    Returns:
        tuple[bool, str, Path, str] | None:
            解析成功时返回 `(dry_run, target, cypher_dir, prefix)`；
            参数不合法时返回 None。
    """

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


def resolve_cypher_files(cypher_dir: Path, prefix: str) -> tuple[Path, Path]:
    """解析待导入的 constraints/import 文件。

    优先固定文件名；若不存在则按 timestamp 后缀配对并选择最新。
    """

    fixed_constraints = cypher_dir / f"{prefix}_constraints.cypher"
    fixed_import = cypher_dir / f"{prefix}_import.cypher"
    if fixed_constraints.is_file() and fixed_import.is_file():
        return fixed_constraints, fixed_import

    ts_pattern = re.compile(r"^(?P<prefix>.+)_(?P<kind>constraints|import)_(?P<ts>\d{8}_\d{6})\.cypher$")
    constraints_ts: set[str] = set()
    import_ts: set[str] = set()

    for path in cypher_dir.glob(f"{prefix}_constraints_*.cypher"):
        match = ts_pattern.match(path.name)
        if match and match.group("prefix") == prefix:
            constraints_ts.add(match.group("ts"))

    for path in cypher_dir.glob(f"{prefix}_import_*.cypher"):
        match = ts_pattern.match(path.name)
        if match and match.group("prefix") == prefix:
            import_ts.add(match.group("ts"))

    common_ts = sorted(constraints_ts & import_ts)
    if not common_ts:
        raise FileNotFoundError(
            "No matched cypher pair found. Expected fixed names "
            f"or timestamped pair under: {cypher_dir} (prefix={prefix})"
        )

    selected_ts = common_ts[-1]
    return (
        cypher_dir / f"{prefix}_constraints_{selected_ts}.cypher",
        cypher_dir / f"{prefix}_import_{selected_ts}.cypher",
    )


def check_container_running(container_name: str) -> tuple[bool, str]:
    """检查目标容器是否处于运行状态。

    Args:
        container_name: 需要匹配的容器名（完全匹配）。

    Returns:
        tuple[bool, str]:
            第一个值表示容器是否在运行；
            第二个值在 `docker ps` 失败时返回错误消息，否则为空字符串。
    """

    cmd = ["docker", "ps", "--format", "{{.Names}}"]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        return False, stderr

    names = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return container_name in names, ""


def run_cypher_file(file_path: Path, config: TargetConfig, phase: str, dry_run: bool) -> int:
    """执行单个 Cypher 文件导入步骤。

    Args:
        file_path: 待执行的 Cypher 文件路径。
        config: 目标容器配置。
        phase: 当前阶段名称（`constraints` 或 `import`）。
        dry_run: 是否仅打印计划命令而不实际执行。

    Returns:
        int: 子进程退出码；成功返回 0。
    """

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
    ]

    if dry_run:
        log.info("%s phase: dry-run command: %s", phase, " ".join(docker_cmd))
        log.info("%s phase: dry-run skipped execution", phase)
        return 0

    cypher_bytes = file_path.read_bytes()
    result = subprocess.run(docker_cmd, input=cypher_bytes, text=False, check=False, capture_output=True)
    if result.returncode == 0:
        log.info("%s phase: success (%s)", phase, file_path)
        return 0

    stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
    stdout = (result.stdout or b"").decode("utf-8", errors="replace").strip()
    if stderr:
        log.error("%s phase: failed (%s), stderr: %s", phase, file_path, stderr)
    elif stdout:
        log.error("%s phase: failed (%s), stdout: %s", phase, file_path, stdout)
    else:
        log.error("%s phase: failed (%s), exit=%s", phase, file_path, result.returncode)
    return result.returncode


def main(argv: list[str]) -> int:
    """命令行主入口。

    Args:
        argv: 命令行参数列表（不含程序名）。

    Returns:
        int: 进程退出码。
    """

    parsed = parse_args(argv)
    if parsed is None:
        return 2

    dry_run, target, cypher_dir, prefix = parsed
    config = TARGETS[target]

    try:
        constraints_path, import_path = resolve_cypher_files(cypher_dir=cypher_dir, prefix=prefix)
    except FileNotFoundError as exc:
        log.error(str(exc))
        return 3

    log.info(
        "Apply config: target=%s container=%s cypher_dir=%s prefix=%s dry_run=%s",
        target,
        config.container,
        cypher_dir,
        prefix,
        dry_run,
    )
    log.info("Selected constraints file: %s", constraints_path)
    log.info("Selected import file: %s", import_path)

    if dry_run:
        rc = run_cypher_file(constraints_path, config, "constraints", dry_run)
        if rc != 0:
            return rc
        rc = run_cypher_file(import_path, config, "import", dry_run)
        if rc != 0:
            return rc
        log.info("All done. Open Neo4j Browser: %s", config.browser_url)
        return 0

    if shutil.which("docker") is None:
        log.error("docker command not found. Please install Docker first.")
        return 127

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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

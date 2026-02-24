#!/usr/bin/env python3
"""将 Graphify 导出的 Cypher 一键导入指定 Neo4j 容器。"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from memory_bench.scripts.bench_logger import logger

GROUP = "neo4j_import"
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


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    创建并返回一个 ``argparse.ArgumentParser``，包含以下参数：

    - ``target``: Neo4j 目标实例名（mem0 / zep / cognee）。
    - ``--constraints``: 约束 Cypher 文件路径。
    - ``--import-file``: 导入 Cypher 文件路径。
    - ``--dry-run``: 仅验证输入并打印计划命令，不实际执行。

    Returns:
        argparse.ArgumentParser: 配置好的参数解析器实例。
    """

    parser = argparse.ArgumentParser(
        description="Apply Cypher files to a Neo4j container via cypher-shell.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Explicit file paths (recommended with latest_file.py --pair-kind cypher):
  uv run python -m memory_bench.scripts.neo4j_apply_cypher mem0 \\
    --constraints graph_constraints_20260224_120000.cypher \\
    --import-file graph_import_20260224_120000.cypher

  # Dry-run:
  uv run python -m memory_bench.scripts.neo4j_apply_cypher mem0 --dry-run \\
    --constraints path/to/constraints.cypher \\
    --import-file path/to/import.cypher
""",
    )
    parser.add_argument(
        "target",
        choices=list(TARGETS.keys()),
        help="Neo4j target instance: mem0 | zep | cognee",
    )
    parser.add_argument(
        "--constraints",
        type=str,
        required=True,
        help="Path to the constraints .cypher file",
    )
    parser.add_argument(
        "--import-file",
        type=str,
        required=True,
        help="Path to the import .cypher file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate inputs and print planned commands without executing docker exec",
    )
    return parser


def check_container_running(container_name: str) -> tuple[bool, str]:
    """检查目标容器是否处于运行状态。

    Args:
        container_name: 需要匹配的容器名（完全匹配）。

    Returns:
        tuple[bool, str]:
            第一个值表示容器是否在运行；
            第二个值在 ``docker ps`` 失败时返回错误消息，否则为空字符串。
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
        phase: 当前阶段名称（``constraints`` 或 ``import``）。
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

    parser = build_parser()
    args = parser.parse_args(argv)

    target: str = args.target
    dry_run: bool = args.dry_run
    constraints_path = Path(args.constraints)
    import_path = Path(args.import_file)
    config = TARGETS[target]

    log.info(
        "Apply config: target=%s container=%s constraints=%s import=%s dry_run=%s",
        target,
        config.container,
        constraints_path,
        import_path,
        dry_run,
    )

    if shutil.which("docker") is None:
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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

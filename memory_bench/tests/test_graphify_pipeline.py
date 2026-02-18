"""graphify_pipeline V0 工作流测试。"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "memory_bench/scripts/graphify_pipeline.py"
FIXTURE_PATH = REPO_ROOT / "memory_bench/tests/fixtures/export_sample.jsonl"
SCRIPTS_DIR = REPO_ROOT / "memory_bench/scripts"


def load_module() -> Any:
    """动态加载 graphify_pipeline 脚本模块。

    Returns:
        Any: 已加载的脚本模块对象。
    """

    unique_name = f"graphify_pipeline_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(unique_name, SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_pipeline_generates_cypher_files(tmp_path: Path) -> None:
    """验证 run pipeline 可在临时目录生成 cypher 文件。

    Args:
        tmp_path: pytest 提供的临时目录。
    """

    module = load_module()
    out_dir = tmp_path / "graphify"
    cypher_out_dir = tmp_path / "neo4j"
    state_db = tmp_path / "state.sqlite"

    graph_artifacts, export_artifacts = module.run_pipeline(
        command="run",
        input_path=FIXTURE_PATH,
        out_dir=out_dir,
        state_db=state_db,
        prefix="graph",
        output_format="jsonl",
        strict=False,
        max_warnings=100,
        warn_duplicate_keys=True,
        cypher_out_dir=cypher_out_dir,
        skip_cypher=False,
    )

    assert graph_artifacts.nodes_path is not None and graph_artifacts.nodes_path.exists()
    assert graph_artifacts.edges_path is not None and graph_artifacts.edges_path.exists()
    assert export_artifacts is not None
    assert export_artifacts.constraints_path is not None and export_artifacts.constraints_path.exists()
    assert export_artifacts.import_path is not None and export_artifacts.import_path.exists()
    assert export_artifacts.report_path.exists()


def test_resolve_skip_cypher_defaults() -> None:
    """验证 resolve_skip_cypher 的默认策略。"""

    module = load_module()
    assert module.resolve_skip_cypher(command="dry-run", cypher_flag=None) is True
    assert module.resolve_skip_cypher(command="run", cypher_flag=None) is False
    assert module.resolve_skip_cypher(command="dry-run", cypher_flag=True) is False


def test_main_dry_run_default_does_not_error(tmp_path: Path) -> None:
    """验证 CLI dry-run 默认跳过 cypher 且不会报错。

    Args:
        tmp_path: pytest 提供的临时目录。
    """

    module = load_module()
    out_dir = tmp_path / "graphify"
    state_db = tmp_path / "state.sqlite"
    argv_backup = sys.argv

    try:
        sys.argv = [
            "graphify_pipeline.py",
            "dry-run",
            "--input",
            str(FIXTURE_PATH),
            "--out-dir",
            str(out_dir),
            "--state-db",
            str(state_db),
        ]
        assert module.main() == 0
    finally:
        sys.argv = argv_backup

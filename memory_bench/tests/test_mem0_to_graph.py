"""mem0_to_graph V0 核心行为测试。"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "memory_bench/scripts/mem0_to_graph.py"
FIXTURE_PATH = REPO_ROOT / "memory_bench/tests/fixtures/export_sample.jsonl"


def load_mem0_to_graph_module():
    """动态加载 mem0_to_graph.py 脚本模块。"""

    unique_name = f"mem0_to_graph_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(unique_name, SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def ensure_fixture_path(tmp_path: Path) -> Path:
    """返回可用 fixture 路径；若仓库 fixture 缺失则在临时目录写入一份。"""

    if FIXTURE_PATH.exists():
        return FIXTURE_PATH

    sample_line = {
        "id": "074bbc5d-2eb3-4859-80db-c4f898e8820c",
        "payload": {
            "scene_id": "chill_ai_chat",
            "character_id": "congyin",
            "conv_id": "ch9998",
            "user_id": "xnne",
            "agent_id": "congyin",
            "data": "很喜欢夏目漱石",
            "hash": "d82ae1eafae11287f949b39cb11dd939",
            "created_at": "2026-02-17T19:12:27.733459-08:00",
            "owner_type": "Character",
            "owner_id": "congyin",
        },
        "collection": "memory_bench_global",
        "isolation": "global",
        "exported_at": "2026-02-18T03:12:42Z",
    }
    fallback = tmp_path / "export_sample.jsonl"
    fallback.write_text(json.dumps(sample_line, ensure_ascii=False) + "\n", encoding="utf-8")
    return fallback


def read_report(path: Path) -> dict[str, Any]:
    """读取 report JSON。"""

    return json.loads(path.read_text(encoding="utf-8"))


def test_compute_processed_key_prefers_hash() -> None:
    """A. payload.hash 优先于顶层 id。"""

    module = load_mem0_to_graph_module()

    assert module.compute_processed_key("abc", {"hash": "h1"}) == "h1"
    assert module.compute_processed_key(123, {"data": "x"}) == "123"


def test_make_node_id_invalid_label_raises() -> None:
    """B. 未知 label 应抛 ValueError。"""

    module = load_mem0_to_graph_module()

    try:
        module.make_node_id("Bogus", "x")
    except ValueError as exc:
        assert "unsupported node label" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("make_node_id should raise ValueError for invalid label")


def test_run_graphify_dry_run_does_not_create_state_db_when_missing(tmp_path: Path) -> None:
    """C. dry-run 在 state 缺失时不创建 sqlite 文件。"""

    module = load_mem0_to_graph_module()
    fixture = ensure_fixture_path(tmp_path)
    out_dir = tmp_path / "out"
    state_db = tmp_path / "state.sqlite"

    artifacts = module.run_graphify(
        command="dry-run",
        input_path=fixture,
        out_dir=out_dir,
        state_db=state_db,
        output_format="jsonl",
        strict=False,
        prefix="graph",
        max_warnings=100,
        warn_duplicate_keys=False,
    )

    assert not state_db.exists()
    assert artifacts.nodes_path is None
    assert artifacts.edges_path is None
    assert artifacts.report_path.exists()

    report = read_report(artifacts.report_path)
    assert report["records_total"] == 1
    assert report["records_valid"] == 1
    # 6 个记录节点 (MemoryItem/User/Agent/Conversation/Scene/Character) + 1 个固定 metadata 节点 (char:xnne)
    assert report["nodes_total"] == 7
    # 8 个记录边 + 2 个固定 metadata 边 (ACTOR + IN_SCENE for agent/user)
    assert report["edges_total"] == 10
    assert report["nodes_path"] == ""
    assert report["edges_path"] == ""


def test_run_graphify_add_creates_state_and_outputs(tmp_path: Path) -> None:
    """D. add 会写出产物并写入 state。"""

    module = load_mem0_to_graph_module()
    fixture = ensure_fixture_path(tmp_path)
    out_dir = tmp_path / "out"
    state_db = tmp_path / "state.sqlite"

    artifacts = module.run_graphify(
        command="add",
        input_path=fixture,
        out_dir=out_dir,
        state_db=state_db,
        output_format="jsonl",
        strict=False,
        prefix="graph",
        max_warnings=100,
        warn_duplicate_keys=True,
    )

    assert state_db.exists()
    assert artifacts.nodes_path is not None and artifacts.nodes_path.exists()
    assert artifacts.edges_path is not None and artifacts.edges_path.exists()

    with sqlite3.connect(state_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM processed_records").fetchone()[0]
        key = conn.execute("SELECT processed_key FROM processed_records LIMIT 1").fetchone()[0]
    assert count == 1
    assert key == "d82ae1eafae11287f949b39cb11dd939"

    nodes_lines = artifacts.nodes_path.read_text(encoding="utf-8").splitlines()
    edges_lines = artifacts.edges_path.read_text(encoding="utf-8").splitlines()
    # 6 个记录节点 + 1 个固定 metadata 节点 (char:xnne)
    assert len(nodes_lines) == 7
    # 8 个记录边 + 2 个固定 metadata 边
    assert len(edges_lines) == 10

    report = read_report(artifacts.report_path)
    assert report["records_valid"] == 1
    assert report["skipped_already_processed"] == 0


def test_run_graphify_add_second_run_skips_duplicates(tmp_path: Path) -> None:
    """E. 第二次 add 同输入应被 state 去重跳过。"""

    module = load_mem0_to_graph_module()
    fixture = ensure_fixture_path(tmp_path)
    out_dir = tmp_path / "out"
    state_db = tmp_path / "state.sqlite"

    module.run_graphify(
        command="add",
        input_path=fixture,
        out_dir=out_dir,
        state_db=state_db,
        output_format="jsonl",
        strict=False,
        prefix="graph",
        max_warnings=100,
        warn_duplicate_keys=True,
    )

    artifacts_second = module.run_graphify(
        command="add",
        input_path=fixture,
        out_dir=out_dir,
        state_db=state_db,
        output_format="jsonl",
        strict=False,
        prefix="graph",
        max_warnings=100,
        warn_duplicate_keys=True,
    )

    report = read_report(artifacts_second.report_path)
    assert report["records_total"] == 1
    assert report["skipped_already_processed"] == 1
    assert report["records_valid"] == 0
    # 即使没有有效记录，固定的 metadata 节点仍然存在 (5 个)
    assert report["nodes_total"] == 5
    # 固定的 metadata 边 (4 个)
    assert report["edges_total"] == 4


def test_warning_truncation_respects_max_warnings(tmp_path: Path) -> None:
    """F. warning 数量超过上限时会截断但统计仍累计。"""

    module = load_mem0_to_graph_module()
    out_dir = tmp_path / "out"
    state_db = tmp_path / "state.sqlite"
    input_path = tmp_path / "many_warnings.jsonl"
    input_path.write_text("\n" * 25, encoding="utf-8")

    artifacts = module.run_graphify(
        command="dry-run",
        input_path=input_path,
        out_dir=out_dir,
        state_db=state_db,
        output_format="jsonl",
        strict=False,
        prefix="graph",
        max_warnings=10,
        warn_duplicate_keys=False,
    )

    report = read_report(artifacts.report_path)
    assert len(report["warnings"]) == 10
    assert report["warnings_truncated"] is True
    assert report["warnings_count_total_estimate"] >= 25

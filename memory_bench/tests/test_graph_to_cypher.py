"""Tests for graph_to_cypher script."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "memory_bench/scripts/graph_to_cypher.py"


def load_module():
    """Dynamically load script module."""

    unique_name = f"graph_to_cypher_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(unique_name, SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fixture_jsonl(path: Path, rows: list[str]) -> None:
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_to_cypher_literal_escapes_single_quote_and_backslash() -> None:
    """_to_cypher_literal should escape quote/backslash as \\' and \\."""

    module = load_module()
    literal = module._to_cypher_literal("a'b\\c")
    assert literal == "'a\\'b\\\\c'"


def test_to_cypher_literal_escapes_backtick_in_dict_key() -> None:
    """dict key backticks should be escaped for Cypher map literal."""

    module = load_module()
    literal = module._to_cypher_literal({"a`b": "x"})
    assert literal == "{`a``b`: 'x'}"


def test_run_export_dry_run_only_writes_report(tmp_path: Path) -> None:
    """dry-run should only create report and leave cypher paths empty in report."""

    module = load_module()
    nodes_path = tmp_path / "nodes.jsonl"
    edges_path = tmp_path / "edges.jsonl"
    out_dir = tmp_path / "out"

    write_fixture_jsonl(
        nodes_path,
        [
            json.dumps({"id": "mem:1", "labels": ["MemoryItem"], "props": {"k": "v"}}),
            json.dumps({"id": "user:1", "labels": ["User"], "props": {"user_id": "1"}}),
        ],
    )
    write_fixture_jsonl(
        edges_path,
        [
            json.dumps(
                {
                    "id": "edge:1",
                    "type": "OWNS_MEMORY",
                    "src": "user:1",
                    "dst": "mem:1",
                    "props": {"processed_key": "h1"},
                }
            )
        ],
    )

    artifacts = module.run_export(nodes_path, edges_path, out_dir, prefix="graph", dry_run=True)

    assert artifacts.report_path.exists()
    assert artifacts.constraints_path is None
    assert artifacts.import_path is None
    assert not (out_dir / "graph_constraints.cypher").exists()
    assert not (out_dir / "graph_import.cypher").exists()

    report = json.loads(artifacts.report_path.read_text(encoding="utf-8"))
    assert report["constraints_path"] == ""
    assert report["import_path"] == ""


def test_run_export_writes_all_outputs_and_counts_valid_rows(tmp_path: Path) -> None:
    """non-dry-run should write all artifacts and count only valid input rows."""

    module = load_module()
    nodes_path = tmp_path / "nodes.jsonl"
    edges_path = tmp_path / "edges.jsonl"
    out_dir = tmp_path / "out"

    write_fixture_jsonl(
        nodes_path,
        [
            json.dumps({"id": "mem:1", "labels": ["MemoryItem"], "props": {"k": "v"}}),
            json.dumps({"id": "user:1", "labels": ["User"], "props": {"user_id": "1"}}),
            json.dumps({"labels": ["BrokenNoId"], "props": {"x": 1}}),
            "{bad-json}",
            "",
        ],
    )
    write_fixture_jsonl(
        edges_path,
        [
            json.dumps(
                {
                    "id": "edge:1",
                    "type": "OWNS_MEMORY",
                    "src": "user:1",
                    "dst": "mem:1",
                    "props": {
                        "processed_key": "h1",
                        "source_point_id": "p1",
                        "exported_at": "2026-01-01T00:00:00Z",
                        "created_at": "2025-12-31T00:00:00Z",
                    },
                }
            ),
            json.dumps({"id": "edge:bad", "type": "OWNS_MEMORY", "src": "", "dst": "mem:1"}),
            "",
        ],
    )

    artifacts = module.run_export(nodes_path, edges_path, out_dir, prefix="graph", dry_run=False)

    assert artifacts.report_path.exists()
    assert artifacts.constraints_path is not None and artifacts.constraints_path.exists()
    assert artifacts.import_path is not None and artifacts.import_path.exists()

    report = json.loads(artifacts.report_path.read_text(encoding="utf-8"))
    assert report["nodes_total"] == 2
    assert report["edges_total"] == 1
    assert report["nodes_by_label"] == {"MemoryItem": 1, "User": 1}
    assert report["edges_by_type"] == {"OWNS_MEMORY": 1}

    import_text = artifacts.import_path.read_text(encoding="utf-8")
    assert "SET r +=" in import_text
    assert "`processed_key`" in import_text
    assert "'h1'" in import_text
    assert "r.props_json" in import_text


def test_run_export_keeps_nested_props_only_in_props_json(tmp_path: Path) -> None:
    """nested dict props should not be written by SET r += map, but remain in props_json."""

    module = load_module()
    nodes_path = tmp_path / "nodes_nested.jsonl"
    edges_path = tmp_path / "edges_nested.jsonl"
    out_dir = tmp_path / "out_nested"

    write_fixture_jsonl(
        nodes_path,
        [
            json.dumps({"id": "mem:1", "labels": ["MemoryItem"], "props": {"k": "v"}}),
            json.dumps({"id": "user:1", "labels": ["User"], "props": {"user_id": "1"}}),
        ],
    )
    write_fixture_jsonl(
        edges_path,
        [
            json.dumps(
                {
                    "id": "edge:1",
                    "type": "OWNS_MEMORY",
                    "src": "user:1",
                    "dst": "mem:1",
                    "props": {
                        "processed_key": "h1",
                        "nested": {"a": 1},
                    },
                }
            )
        ],
    )

    artifacts = module.run_export(nodes_path, edges_path, out_dir, prefix="graph", dry_run=False)
    import_text = artifacts.import_path.read_text(encoding="utf-8")

    assert "r.props_json" in import_text
    assert '"nested": {"a": 1}' in import_text
    assert "`nested`" not in import_text
    assert "`processed_key`" in import_text
    assert "'h1'" in import_text

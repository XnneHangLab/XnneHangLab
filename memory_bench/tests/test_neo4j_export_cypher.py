"""neo4j_export_cypher 基础行为测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "memory_bench/scripts/neo4j_export_cypher.py"


def load_module():
    """动态加载脚本模块。"""

    unique_name = f"neo4j_export_cypher_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(unique_name, SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_export_outputs_and_report(tmp_path: Path) -> None:
    """写出 cypher 与 report，且统计值正确。"""

    module = load_module()
    nodes_path = tmp_path / "graph_nodes_demo.jsonl"
    edges_path = tmp_path / "graph_edges_demo.jsonl"
    out_dir = tmp_path / "out"

    nodes_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "memory:1", "labels": ["MemoryItem"], "props": {"k": "v"}}, ensure_ascii=False),
                "{broken-json}",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    edges_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "edge:1",
                        "type": "OWNS_MEMORY",
                        "src": "user:1",
                        "dst": "memory:1",
                        "props": {"processed_key": "h1"},
                    },
                    ensure_ascii=False,
                ),
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    artifacts = module.run_export(
        nodes_path=nodes_path,
        edges_path=edges_path,
        out_dir=out_dir,
        prefix="graph",
        dry_run=False,
    )

    assert artifacts.constraints_path is not None and artifacts.constraints_path.exists()
    assert artifacts.import_path is not None and artifacts.import_path.exists()
    assert artifacts.report_path.exists()

    report = json.loads(artifacts.report_path.read_text(encoding="utf-8"))
    assert report["nodes_total"] == 1
    assert report["edges_total"] == 1
    assert report["nodes_by_label"] == {"MemoryItem": 1}
    assert report["edges_by_type"] == {"OWNS_MEMORY": 1}
    assert report["skipped_invalid_json"] == 1
    assert report["skipped_empty_line"] == 2

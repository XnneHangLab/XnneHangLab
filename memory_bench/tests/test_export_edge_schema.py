#!/usr/bin/env python3
"""`export_edge_schema.py` 的解析与文档渲染测试。

说明：
    该测试文件聚焦于非公开测试入口的行为校验，
    主要验证 CSV/Map 解析与 Markdown 关键片段输出。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "export_edge_schema.py"

spec = importlib.util.spec_from_file_location("export_edge_schema", SCRIPT_PATH)
assert spec is not None and spec.loader is not None, f"Cannot load spec from {SCRIPT_PATH}"
export_edge_schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_edge_schema)

parse_cypher_output = export_edge_schema.parse_cypher_output
generate_markdown_report = export_edge_schema.generate_markdown_report


def test_parse_edge_row_with_map_fields():
    """验证边行中嵌套 Map 字段可以被正确解析为字典。"""
    output = """edge_type, relationship, src_label, src_id, dst_label, dst_id, edge_properties
"ABOUT", {identity: 138, type: "ABOUT", properties: {predicate: "PREFERS_TOPIC"}}, "Node", "claim:aaa", "Node", "topic:bbb", {predicate: "PREFERS_TOPIC", type: "ABOUT"}"""

    rows = parse_cypher_output(output)
    assert len(rows) == 1
    row = rows[0]
    assert row["edge_type"] == "ABOUT"
    assert row["src_id"] == "claim:aaa"
    assert row["dst_id"] == "topic:bbb"
    assert isinstance(row["relationship"], dict)
    assert row["relationship"]["type"] == "ABOUT"
    assert isinstance(row["edge_properties"], dict)
    assert row["edge_properties"]["predicate"] == "PREFERS_TOPIC"


def test_markdown_contains_relationship_summary_table_at_bottom():
    """验证 Markdown 在底部追加关系汇总表格。"""
    data = {
        "generated_at": "2026-03-01T00:00:00+08:00",
        "neo4j_container": "membench-neo4j-mem0",
        "edge_examples_by_id_prefix": [],
        "edge_examples_by_type": [
            {
                "edge_type": "ABOUT",
                "src_label": "Node",
                "src_id": "claim:aaa",
                "dst_label": "Node",
                "dst_id": "topic:bbb",
                "relationship": {"type": "ABOUT"},
                "edge_properties": {"type": "ABOUT"},
            }
        ],
    }

    md = generate_markdown_report(data)
    assert "## 关系示例（每个类型一个完整示例）" in md
    assert "| 关系类型 | 源节点 | 源节点 ID | 目标节点 | 目标节点 ID |" in md
    assert "| ABOUT | Node | claim:aaa | Node | topic:bbb |" in md

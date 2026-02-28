#!/usr/bin/env python3
"""Tests for export_edge_schema.py CSV/JSON parsing logic."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "export_edge_schema.py"

spec = importlib.util.spec_from_file_location("export_edge_schema", SCRIPT_PATH)
export_edge_schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_edge_schema)

parse_cypher_output = export_edge_schema.parse_cypher_output


def test_parse_edge_row_with_map_fields():
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

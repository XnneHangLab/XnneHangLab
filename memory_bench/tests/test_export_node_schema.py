#!/usr/bin/env python3
"""Tests for export_node_schema.py CSV/JSON parsing logic."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


# Import the module under test
SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "export_node_schema.py"

spec = importlib.util.spec_from_file_location("export_node_schema", SCRIPT_PATH)
export_schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_schema)

split_csv_line = export_schema.split_csv_line
convert_neo4j_map_to_json = export_schema.convert_neo4j_map_to_json
parse_cypher_output = export_schema.parse_cypher_output


class TestSplitCsvLine:
    """Test split_csv_line() function."""

    def test_simple_csv(self):
        """Test simple CSV without nested structures."""
        line = "a, b, c"
        result = split_csv_line(line)
        assert result == ["a", " b", " c"]

    def test_csv_with_quotes(self):
        """Test CSV with quoted values."""
        line = '"hello, world", "test"'
        result = split_csv_line(line)
        assert result == ['"hello, world"', ' "test"']

    def test_csv_with_nested_braces(self):
        """Test CSV with nested {} structures."""
        line = "a, b, {x: 1, y: 2}"
        result = split_csv_line(line)
        assert result == ["a", " b", " {x: 1, y: 2}"]

    def test_csv_with_nested_brackets(self):
        """Test CSV with nested [] structures."""
        line = "a, b, [1, 2, 3]"
        result = split_csv_line(line)
        assert result == ["a", " b", " [1, 2, 3]"]

    def test_csv_with_deep_nesting(self):
        """Test CSV with deeply nested structures."""
        line = "a, {x: [1, 2], y: {z: 3}}, b"
        result = split_csv_line(line)
        assert result == ["a", " {x: [1, 2], y: {z: 3}}", " b"]

    def test_neo4j_output_format(self):
        """Test actual Neo4j output format."""
        line = '"MemoryItem", "mem:xxx", {name: "test", data: "hello, world"}'
        result = split_csv_line(line)
        assert len(result) == 3
        assert result[0] == '"MemoryItem"'
        assert result[1] == ' "mem:xxx"'
        assert "{" in result[2] and "}" in result[2]


class TestConvertNeo4jMapToJson:
    """Test convert_neo4j_map_to_json() function."""

    def test_simple_map(self):
        """Test simple Neo4j Map conversion."""
        neo4j_map = '{name: "congyin", id: "char:congyin"}'
        result = convert_neo4j_map_to_json(neo4j_map)
        parsed = json.loads(result)
        assert parsed == {"name": "congyin", "id": "char:congyin"}

    def test_map_with_empty_arrays(self):
        """Test Neo4j Map with empty arrays."""
        neo4j_map = '{aliases: [], entity_type: "Agent", tags: []}'
        result = convert_neo4j_map_to_json(neo4j_map)
        parsed = json.loads(result)
        assert parsed["aliases"] == []
        assert parsed["entity_type"] == "Agent"
        assert parsed["tags"] == []

    def test_map_with_nested_objects(self):
        """Test Neo4j Map with nested structures."""
        neo4j_map = '{name: "test", data: {x: 1, y: 2}}'
        result = convert_neo4j_map_to_json(neo4j_map)
        parsed = json.loads(result)
        assert parsed["name"] == "test"
        assert parsed["data"] == {"x": 1, "y": 2}

    def test_map_with_special_characters(self):
        """Test Neo4j Map with special characters in values."""
        neo4j_map = '{data: "[User] 会使用一个小杯子来给茶散热。", id: "mem:xxx"}'
        result = convert_neo4j_map_to_json(neo4j_map)
        parsed = json.loads(result)
        assert parsed["data"] == "[User] 会使用一个小杯子来给茶散热。"
        assert parsed["id"] == "mem:xxx"


class TestParseCypherOutput:
    """Test parse_cypher_output() function."""

    def test_simple_csv_output(self):
        """Test parsing simple CSV output."""
        output = """label, count
"Node", 41
"MemoryItem", 11"""
        result = parse_cypher_output(output)
        assert len(result) == 2
        assert result[0] == {"label": "Node", "count": "41"}
        assert result[1] == {"label": "MemoryItem", "count": "11"}

    def test_csv_with_json_field(self):
        """Test parsing CSV with JSON field."""
        output = """node_type, id, all_props
"MemoryItem", "mem:xxx", {name: "test", data: "hello"}"""
        result = parse_cypher_output(output)
        assert len(result) == 1
        assert result[0]["node_type"] == "MemoryItem"
        assert result[0]["id"] == "mem:xxx"
        assert isinstance(result[0]["all_props"], dict)
        assert result[0]["all_props"]["name"] == "test"
        assert result[0]["all_props"]["data"] == "hello"

    def test_neo4j_export_format(self):
        """Test parsing actual Neo4j export format."""
        output = """node_type, id, name, display, all_props
"Agent", "agent:congyin", "congyin", "congyin", {aliases: [], entity_type: "Agent", agent_id: "congyin"}
"Character", "char:congyin", "congyin", "congyin", {name: "congyin", character_id: "congyin"}"""
        result = parse_cypher_output(output)
        assert len(result) == 2

        # Check first row
        assert result[0]["node_type"] == "Agent"
        assert result[0]["id"] == "agent:congyin"
        assert isinstance(result[0]["all_props"], dict)
        assert result[0]["all_props"]["entity_type"] == "Agent"
        assert result[0]["all_props"]["agent_id"] == "congyin"
        assert result[0]["all_props"]["aliases"] == []

        # Check second row
        assert result[1]["node_type"] == "Character"
        assert result[1]["id"] == "char:congyin"
        assert result[1]["all_props"]["character_id"] == "congyin"

    def test_empty_output(self):
        """Test parsing empty output."""
        result = parse_cypher_output("")
        assert result == []

    def test_single_line_output(self):
        """Test parsing single line (header only)."""
        output = "label, count"
        result = parse_cypher_output(output)
        assert result == []

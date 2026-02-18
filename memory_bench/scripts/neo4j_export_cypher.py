#!/usr/bin/env python3
"""Convert graphify_export(V0) nodes/edges JSONL into Neo4j import Cypher files.

V0 notes:
- Relationship `props` are always preserved in `r.props_json` as full-fidelity fallback.
- `SET r += <map>` only writes Neo4j property-compatible values (primitive/list-of-primitive).
  Non-compatible nested structures are intentionally skipped from top-level relationship attrs.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ExportArtifacts:
    """Output artifact paths for one export run."""

    constraints_path: Path | None
    import_path: Path | None
    report_path: Path


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(
        description="Convert graphify_export(V0) nodes/edges JSONL into Neo4j import cypher files",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--nodes", required=True, type=str, help="Path to graph_nodes_*.jsonl")
    parser.add_argument("--edges", required=True, type=str, help="Path to graph_edges_*.jsonl")
    parser.add_argument("--out-dir", required=True, type=str, help="Output directory")
    parser.add_argument("--prefix", default="graph", type=str, help="Output filename prefix")
    parser.add_argument("--dry-run", action="store_true", help="Only parse/stat; do not write cypher")
    return parser


def _escape_cypher_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _escape_cypher_identifier(value: str) -> str:
    """Escape Cypher backtick identifier by doubling backticks."""

    return value.replace("`", "``")


def _is_neo4j_property_value(value: Any) -> bool:
    """Return True when value is Neo4j property-compatible.

    Neo4j property values support primitive scalars and list of primitive scalars.
    """

    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(item is None or isinstance(item, (bool, int, float, str)) for item in value)
    return False


def _to_cypher_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return f"'{_escape_cypher_string(value)}'"
    if isinstance(value, list):
        return "[" + ", ".join(_to_cypher_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            parts.append(f"`{_escape_cypher_identifier(str(key))}`: {_to_cypher_literal(item)}")
        return "{" + ", ".join(parts) + "}"
    return f"'{_escape_cypher_string(json.dumps(value, ensure_ascii=False))}'"


def _normalize_labels(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    normalized: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        label = item.strip()
        if label:
            normalized.append(label)
    return normalized


def _read_jsonl(path: Path, stats: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for raw in fp:
            stripped = raw.strip()
            if not stripped:
                stats["skipped_empty_line"] += 1
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                stats["skipped_invalid_json"] += 1
                continue
            if not isinstance(obj, dict):
                stats[f"skipped_invalid_{kind}"] += 1
                continue
            rows.append(obj)
    return rows


def _build_constraints_cypher() -> str:
    return "\n".join(
        [
            "// Auto-generated constraints for graphify_export(V0)",
            "CREATE CONSTRAINT node_id_unique IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE;",
            "CREATE CONSTRAINT rel_id_unique IF NOT EXISTS FOR ()-[r:REL]-() REQUIRE r.id IS UNIQUE;",
            "",
        ]
    )


def _build_node_merge(node: dict[str, Any]) -> str | None:
    node_id = node.get("id")
    if node_id is None or str(node_id).strip() == "":
        return None

    labels = _normalize_labels(node.get("labels"))
    props = node.get("props") if isinstance(node.get("props"), dict) else {}
    labels_clause = "".join(f":`{label}`" for label in labels)
    return (
        f"MERGE (n:Node {{id: {_to_cypher_literal(str(node_id))}}}) "
        f"SET n += {_to_cypher_literal(props)} "
        f"SET n{labels_clause};"
    )


def _build_edge_merge(edge: dict[str, Any]) -> str | None:
    edge_id = edge.get("id")
    edge_type = edge.get("type")
    src = edge.get("src")
    dst = edge.get("dst")
    if any(v is None or str(v).strip() == "" for v in (edge_id, edge_type, src, dst)):
        return None

    props_raw = edge.get("props") if isinstance(edge.get("props"), dict) else {}
    props_for_set = {
        key: value for key, value in props_raw.items() if _is_neo4j_property_value(value)
    }
    props_json = json.dumps(props_raw, ensure_ascii=False)
    return "\n".join(
        [
            f"MATCH (s:Node {{id: {_to_cypher_literal(str(src))}}})",
            f"MATCH (t:Node {{id: {_to_cypher_literal(str(dst))}}})",
            f"MERGE (s)-[r:REL {{id: {_to_cypher_literal(str(edge_id))}}}]->(t)",
            (
                f"SET r.type = {_to_cypher_literal(str(edge_type))}, "
                f"r.src = {_to_cypher_literal(str(src))}, "
                f"r.dst = {_to_cypher_literal(str(dst))}, "
                f"r.props_json = {_to_cypher_literal(props_json)}"
            ),
            f"SET r += {_to_cypher_literal(props_for_set)};",
        ]
    )


def run_export(nodes_path: Path, edges_path: Path, out_dir: Path, prefix: str, dry_run: bool) -> ExportArtifacts:
    """Run export and emit report/cypher artifacts."""

    stats: dict[str, Any] = {
        "nodes_total": 0,
        "edges_total": 0,
        "nodes_by_label": {},
        "edges_by_type": {},
        "skipped_empty_line": 0,
        "skipped_invalid_json": 0,
        "skipped_invalid_node": 0,
        "skipped_invalid_edge": 0,
    }

    node_rows = _read_jsonl(nodes_path, stats, kind="node")
    edge_rows = _read_jsonl(edges_path, stats, kind="edge")

    nodes_by_label: dict[str, int] = defaultdict(int)
    edges_by_type: dict[str, int] = defaultdict(int)
    node_merges: list[str] = []
    edge_merges: list[str] = []

    for node in node_rows:
        merge_stmt = _build_node_merge(node)
        if merge_stmt is None:
            stats["skipped_invalid_node"] += 1
            continue
        node_merges.append(merge_stmt)
        stats["nodes_total"] += 1
        for label in _normalize_labels(node.get("labels")):
            nodes_by_label[label] += 1

    for edge in edge_rows:
        merge_stmt = _build_edge_merge(edge)
        if merge_stmt is None:
            stats["skipped_invalid_edge"] += 1
            continue
        edge_merges.append(merge_stmt)
        stats["edges_total"] += 1
        edges_by_type[str(edge.get("type"))] += 1

    stats["nodes_by_label"] = dict(sorted(nodes_by_label.items()))
    stats["edges_by_type"] = dict(sorted(edges_by_type.items()))

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{prefix}_report.json"
    constraints_path = out_dir / f"{prefix}_constraints.cypher"
    import_path = out_dir / f"{prefix}_import.cypher"

    if not dry_run:
        constraints_path.write_text(_build_constraints_cypher(), encoding="utf-8")
        import_body = [
            "// Auto-generated import cypher for graphify_export(V0)",
            "// Nodes",
            *node_merges,
            "",
            "// Relationships",
            *edge_merges,
            "",
        ]
        import_path.write_text("\n".join(import_body), encoding="utf-8")
    else:
        constraints_path = None
        import_path = None

    report = {
        **stats,
        "nodes_input": str(nodes_path),
        "edges_input": str(edges_path),
        "dry_run": dry_run,
        "constraints_path": str(constraints_path) if constraints_path else "",
        "import_path": str(import_path) if import_path else "",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return ExportArtifacts(constraints_path=constraints_path, import_path=import_path, report_path=report_path)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_export(
        nodes_path=Path(args.nodes),
        edges_path=Path(args.edges),
        out_dir=Path(args.out_dir),
        prefix=args.prefix,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

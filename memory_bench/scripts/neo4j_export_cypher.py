#!/usr/bin/env python3
"""将 graphify_export(V0) 的 nodes/edges JSONL 转为 Neo4j 可导入 Cypher 文件。

V0 约定说明：
- 关系原始 `props` 会完整保存在 `r.props_json`，用于兜底与回溯。
- `SET r += <map>` 只投影 Neo4j 支持的属性类型（标量或标量列表）。
- 对于嵌套 dict/list[dict] 等不受支持类型，不会直接写为关系顶层属性。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ExportArtifacts:
    """描述一次导出任务的产物路径。

    Attributes:
        constraints_path: 约束 Cypher 文件路径；`dry-run` 时为 None。
        import_path: 导入 Cypher 文件路径；`dry-run` 时为 None。
        report_path: 统计报告 JSON 文件路径。
    """

    constraints_path: Path | None
    import_path: Path | None
    report_path: Path


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        argparse.ArgumentParser: 已配置输入/输出参数的解析器。
    """

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
    """转义 Cypher 字符串字面量中的特殊字符。

    Args:
        value: 原始字符串。

    Returns:
        str: 完成反斜线与单引号转义后的字符串。
    """

    return value.replace("\\", "\\\\").replace("'", "\\'")


def _escape_cypher_key(value: str) -> str:
    """转义 Cypher map key 中的反引号。

    Args:
        value: 原始 key 文本。

    Returns:
        str: 将反引号翻倍后的可安全嵌入值。
    """

    return value.replace("`", "``")


def _escape_cypher_rel_type(value: str) -> str:
    """转义关系类型标识符中的反引号。

    Args:
        value: 原始关系类型文本。

    Returns:
        str: 将反引号翻倍后的可安全嵌入值。
    """

    return value.replace("`", "``")


def _is_neo4j_prop_value(value: Any) -> bool:
    """判断值是否可作为 Neo4j 属性写入。

    支持类型：None、bool、int、float、str，以及上述类型构成的 list。

    Args:
        value: 待判断值。

    Returns:
        bool: True 表示可安全用于 `SET r +=`，False 表示应仅保留在 `props_json`。
    """

    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(item is None or isinstance(item, (bool, int, float, str)) for item in value)
    return False


def _filter_neo4j_props(props: dict[str, Any]) -> dict[str, Any]:
    """过滤可安全写入 Neo4j 顶层属性的键值。

    Args:
        props: 原始关系属性字典。

    Returns:
        dict[str, Any]: 仅包含 Neo4j property-compatible 值的新字典。
    """

    return {str(key): value for key, value in props.items() if _is_neo4j_prop_value(value)}


def _to_cypher_literal(value: Any) -> str:
    """将 Python 值编码为 Cypher 字面量。

    Args:
        value: 待编码值。

    Returns:
        str: 可直接拼接到 Cypher 语句中的字面量文本。
    """

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
            parts.append(f"`{_escape_cypher_key(str(key))}`: {_to_cypher_literal(item)}")
        return "{" + ", ".join(parts) + "}"
    return f"'{_escape_cypher_string(json.dumps(value, ensure_ascii=False))}'"


def _normalize_labels(raw: Any) -> list[str]:
    """规范化节点标签列表。

    Args:
        raw: 原始 `labels` 字段值。

    Returns:
        list[str]: 过滤非字符串与空白后的标签列表。
    """

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
    """读取并严格解析 JSONL 文件。

    解析规则：
    - 空行跳过并累计 `skipped_empty_line`
    - 非法 JSON 累计 `skipped_invalid_json`
    - 非对象 JSON 累计 `skipped_invalid_{kind}`

    Args:
        path: 输入 JSONL 文件路径。
        stats: 统计字典（原地更新）。
        kind: 数据类型名称（`node` 或 `edge`）。

    Returns:
        list[dict[str, Any]]: 解析成功且为对象的记录列表。
    """

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


def _build_constraints_cypher(edge_types: list[str]) -> str:
    """构建 Neo4j 约束 Cypher 文本。

    Args:
        edge_types: 已规范化的关系类型集合。

    Returns:
        str: 包含节点/关系唯一约束的脚本内容。
    """

    lines = [
        "// Auto-generated constraints for graphify_export(V0)",
        "CREATE CONSTRAINT node_id_unique IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE;",
    ]
    for edge_type in edge_types:
        edge_type_escaped = _escape_cypher_rel_type(edge_type)
        safe_constraint_type = re.sub(r"[^0-9A-Za-z_]", "_", edge_type).strip("_")
        if not safe_constraint_type:
            safe_constraint_type = "REL"
        lines.append(
            "CREATE CONSTRAINT "
            f"rel_{safe_constraint_type}_id_unique IF NOT EXISTS "
            f"FOR ()-[r:`{edge_type_escaped}`]-() REQUIRE r.id IS UNIQUE;"
        )
    lines.append("")
    return "\n".join(lines)


def _build_node_merge(node: dict[str, Any]) -> str | None:
    """构建单条节点导入语句。

    Args:
        node: 单条节点对象，期望包含 `id`、`labels`、`props` 字段。

    Returns:
        str | None: 可执行的 MERGE+SET 语句；若节点缺失有效 id 则返回 None。
    """

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
    """构建单条关系导入语句。

    Args:
        edge: 单条边对象，期望包含 `id`、`type`、`src`、`dst` 与可选 `props`。

    Returns:
        str | None: 关系 MATCH+MERGE+SET 语句；关键字段缺失时返回 None。
    """

    edge_id = edge.get("id")
    edge_type = edge.get("type")
    src = edge.get("src")
    dst = edge.get("dst")
    if any(v is None or str(v).strip() == "" for v in (edge_id, edge_type, src, dst)):
        return None

    props_raw = edge.get("props") if isinstance(edge.get("props"), dict) else {}
    props_filtered = _filter_neo4j_props(props_raw)
    props_json = json.dumps(props_raw, ensure_ascii=False)
    edge_type_escaped = _escape_cypher_rel_type(str(edge_type))
    return "\n".join(
        [
            f"MATCH (s:Node {{id: {_to_cypher_literal(str(src))}}})",
            f"MATCH (t:Node {{id: {_to_cypher_literal(str(dst))}}})",
            f"MERGE (s)-[r:`{edge_type_escaped}` {{id: {_to_cypher_literal(str(edge_id))}}}]->(t)",
            (
                f"SET r.type = {_to_cypher_literal(str(edge_type))}, "
                f"r.src = {_to_cypher_literal(str(src))}, "
                f"r.dst = {_to_cypher_literal(str(dst))}, "
                f"r.props_json = {_to_cypher_literal(props_json)}"
            ),
            f"SET r += {_to_cypher_literal(props_filtered)};",
        ]
    )


def _utc_timestamp() -> str:
    """生成 UTC 时间戳（YYYYMMDD_HHMMSS）。

    Returns:
        str: UTC 时间戳字符串。
    """

    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def run_export(nodes_path: Path, edges_path: Path, out_dir: Path, prefix: str, dry_run: bool) -> ExportArtifacts:
    """执行转换并写出产物。

    Args:
        nodes_path: 节点 JSONL 输入路径。
        edges_path: 边 JSONL 输入路径。
        out_dir: 输出目录。
        prefix: 输出文件名前缀。
        dry_run: 是否仅统计不写 Cypher 文件。

    Returns:
        ExportArtifacts: 本次执行生成的产物路径。
    """

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
    edge_types = sorted(edge_type for edge_type in edges_by_type.keys() if edge_type.strip())

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_timestamp()
    report_path = out_dir / f"{prefix}_report_{timestamp}.json"
    constraints_path = out_dir / f"{prefix}_constraints_{timestamp}.cypher"
    import_path = out_dir / f"{prefix}_import_{timestamp}.cypher"

    if not dry_run:
        constraints_path.write_text(_build_constraints_cypher(edge_types), encoding="utf-8")
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
        "timestamp": timestamp,
        "nodes_input": str(nodes_path),
        "edges_input": str(edges_path),
        "dry_run": dry_run,
        "constraints_path": str(constraints_path) if constraints_path else "",
        "import_path": str(import_path) if import_path else "",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return ExportArtifacts(constraints_path=constraints_path, import_path=import_path, report_path=report_path)


def main() -> None:
    """命令行入口。"""

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

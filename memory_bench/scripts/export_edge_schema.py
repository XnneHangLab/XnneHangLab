#!/usr/bin/env python3
"""导出 Neo4j 图谱的边 Schema 示例（按边 ID 前缀 + 关系类型）。

用法：
    uv run memory_bench/scripts/export_edge_schema.py
    uv run memory_bench/scripts/export_edge_schema.py --format json
    uv run memory_bench/scripts/export_edge_schema.py --output custom_path.md

自动读取 memory_bench/.env.benchmark 中的 Neo4j 配置：
- NEO4J_CONTAINER
- NEO4J_USER
- NEO4J_PASSWORD

输出：
- 默认：memory_bench/docs/08_EDGE_SCHEMA_REFERENCE.md
- JSON 格式：memory_bench/docs/08_EDGE_SCHEMA_REFERENCE.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_bench.scripts.bench_logger import logger

log = logger.bind(group="export_edge_schema")

try:
    from dotenv import load_dotenv  # type: ignore[reportMissingImports,reportUnknownVariableType]
except ImportError:
    load_dotenv = None
    log.warning("未安装 python-dotenv，跳过 .env.benchmark 自动加载")

ENV_FILE = Path(__file__).parent.parent / ".env.benchmark"
if ENV_FILE.exists():
    if load_dotenv is not None:
        load_dotenv(ENV_FILE)
        log.info("已加载配置文件：%s", ENV_FILE)
    else:
        log.warning("检测到 %s 但未安装 python-dotenv，改用当前环境变量", ENV_FILE)
else:
    log.warning("配置文件不存在：%s，使用默认值", ENV_FILE)

NEO4J_CONTAINER = os.getenv("NEO4J_CONTAINER", "membench-neo4j-mem0")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4jneo4j")

log.info("Neo4j 配置：容器=%s, 用户=%s", NEO4J_CONTAINER, NEO4J_USER)

QUERY_EDGES_BY_ID_PREFIX = """
// 查询边完整信息：按边 id 前缀分类（每类一个示例）
MATCH (src)-[r]->(dst)
WHERE r.id IS NOT NULL
WITH
  CASE
    WHEN r.id CONTAINS ":" THEN split(r.id, ":")[0]
    ELSE "other"
  END AS edge_id_prefix,
  collect({rel: r, src: src, dst: dst})[0] AS example
RETURN
  edge_id_prefix,
  type(example.rel) AS edge_type,
  example.rel AS relationship,
  labels(example.src)[0] AS src_label,
  example.src.id AS src_id,
  labels(example.dst)[0] AS dst_label,
  example.dst.id AS dst_id,
  properties(example.rel) AS edge_properties
ORDER BY edge_id_prefix
"""

QUERY_EDGES_BY_TYPE = """
// 查询边完整信息：按关系类型去重（每个关系类型一个示例）
MATCH (src)-[r]->(dst)
WITH type(r) AS edge_type, collect({rel: r, src: src, dst: dst})[0] AS example
RETURN
  edge_type,
  example.rel AS relationship,
  labels(example.src)[0] AS src_label,
  example.src.id AS src_id,
  labels(example.dst)[0] AS dst_label,
  example.dst.id AS dst_id,
  properties(example.rel) AS edge_properties
ORDER BY edge_type
"""


def run_cypher(
    cypher_text: str,
    *,
    container: str = NEO4J_CONTAINER,
    user: str = NEO4J_USER,
    password: str = NEO4J_PASSWORD,
) -> tuple[bool, str]:
    """在 Neo4j 容器内执行 Cypher 查询。

    Args:
        cypher_text: 要执行的 Cypher 文本。
        container: Neo4j Docker 容器名。
        user: Neo4j 用户名。
        password: Neo4j 密码。

    Returns:
        tuple[bool, str]: 二元组 `(ok, output)`。
        - `ok=True` 表示执行成功，`output` 为标准输出文本。
        - `ok=False` 表示执行失败，`output` 为错误信息。
    """
    cmd = [
        "docker",
        "exec",
        "-i",
        container,
        "cypher-shell",
        "-u",
        user,
        "-p",
        password,
        "--format",
        "plain",
    ]

    try:
        result = subprocess.run(
            cmd,
            input=cypher_text.encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=60,
        )
    except FileNotFoundError:
        return False, "docker 命令未找到"
    except subprocess.TimeoutExpired:
        return False, "查询超时（60 秒）"

    if result.returncode == 0:
        return True, (result.stdout or b"").decode("utf-8", errors="replace")

    stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
    stdout = (result.stdout or b"").decode("utf-8", errors="replace").strip()
    msg = stderr or stdout or f"exit code {result.returncode}"
    return False, msg


def split_csv_line(line: str) -> list[str]:
    """按 CSV 规则拆分一行文本，支持嵌套对象与数组。

    该函数用于解析 `cypher-shell --format plain` 输出，避免在
    Neo4j Map（`{}`）或数组（`[]`）内部错误分割逗号。

    Args:
        line: 一行待拆分的文本。

    Returns:
        list[str]: 拆分后的字段列表（保留原始空格与引号形态）。
    """
    result: list[str] = []
    current: list[str] = []
    brace_depth = 0
    bracket_depth = 0
    in_quotes = False

    for char in line:
        if char == '"' and (not current or current[-1] != "\\"):
            in_quotes = not in_quotes
            current.append(char)
        elif char == "{" and not in_quotes:
            brace_depth += 1
            current.append(char)
        elif char == "}" and not in_quotes:
            brace_depth -= 1
            current.append(char)
        elif char == "[" and not in_quotes:
            bracket_depth += 1
            current.append(char)
        elif char == "]" and not in_quotes:
            bracket_depth -= 1
            current.append(char)
        elif char == "," and brace_depth == 0 and bracket_depth == 0 and not in_quotes:
            result.append("".join(current))
            current = []
        else:
            current.append(char)

    if current:
        result.append("".join(current))

    return result


def convert_neo4j_map_to_json(neo4j_map: str) -> str:
    """将 Neo4j Map 风格字符串转换为标准 JSON 字符串。

    示例：`{name: "a", tags: []}` -> `{"name": "a", "tags": []}`。

    Args:
        neo4j_map: Neo4j Map 格式字符串。

    Returns:
        str: 尽可能可被 `json.loads` 解析的 JSON 字符串。
    """
    result = neo4j_map
    result = re.sub(r"([{,]\s*)(\w+)(\s*:)", r'\1"\2"\3', result)
    result = result.replace("'", '"')
    return result


def parse_cypher_output(output: str) -> list[dict[str, Any]]:
    """解析 cypher-shell plain 输出为结构化字典列表。

    Args:
        output: `cypher-shell --format plain` 的原始输出文本。

    Returns:
        list[dict[str, Any]]: 逐行解析后的结果。
        当字段值是 Neo4j Map 且可转换时，会转为 Python `dict`。
    """
    lines = output.strip().split("\n")
    if len(lines) < 2:
        return []

    headers = [h.strip().strip('"') for h in split_csv_line(lines[0])]
    rows: list[dict[str, Any]] = []

    for line in lines[1:]:
        if not line.strip():
            continue

        values = split_csv_line(line)
        if len(values) != len(headers):
            continue

        row_dict: dict[str, Any] = {}
        for i, key in enumerate(headers):
            value = values[i].strip().strip('"')
            if value.startswith("{") and value.endswith("}"):
                try:
                    json_str = convert_neo4j_map_to_json(value)
                    row_dict[key] = json.loads(json_str)
                except (json.JSONDecodeError, ValueError):
                    row_dict[key] = value
            else:
                row_dict[key] = value
        rows.append(row_dict)

    return rows


def generate_edge_schema_data(container: str) -> dict[str, Any]:
    """查询并构建边 Schema 的统一数据结构。

    Args:
        container: Neo4j Docker 容器名。

    Returns:
        dict[str, Any]: 包含生成时间、容器名、
        按边 ID 前缀示例与按关系类型示例的数据字典。
    """
    data: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),  # noqa: UP017
        "neo4j_container": container,
        "edge_examples_by_id_prefix": [],
        "edge_examples_by_type": [],
    }

    log.info("查询边示例（按 ID 前缀）...")
    ok, output = run_cypher(QUERY_EDGES_BY_ID_PREFIX, container=container)
    if ok:
        data["edge_examples_by_id_prefix"] = parse_cypher_output(output)
        log.info("边示例（ID 前缀）：%d 个", len(data["edge_examples_by_id_prefix"]))
    else:
        log.error("边示例（ID 前缀）查询失败：%s", output)

    log.info("查询关系示例（按关系类型）...")
    ok, output = run_cypher(QUERY_EDGES_BY_TYPE, container=container)
    if ok:
        data["edge_examples_by_type"] = parse_cypher_output(output)
        log.info("关系示例（关系类型）：%d 个", len(data["edge_examples_by_type"]))
    else:
        log.error("关系示例（关系类型）查询失败：%s", output)

    return data


def render_edge_example_block(row: dict[str, Any], title: str) -> list[str]:
    """将单条边示例渲染为 Markdown 片段。

    Args:
        row: 单条边示例数据。
        title: 当前小节标题（例如边前缀或关系类型）。

    Returns:
        list[str]: Markdown 片段行列表。
    """
    edge_type = row.get("edge_type", "")
    relationship = row.get("relationship", "")
    src_label = row.get("src_label", "")
    src_id = row.get("src_id", "")
    dst_label = row.get("dst_label", "")
    dst_id = row.get("dst_id", "")
    edge_properties = row.get("edge_properties", "")

    block: list[str] = []
    block.append(f"\n### {title}\n")
    block.append(f"- **Edge Type**: {edge_type}\n")
    block.append(f"- **Source**: {src_label} / {src_id}\n")
    block.append(f"- **Target**: {dst_label} / {dst_id}\n")

    if isinstance(relationship, dict):
        block.append("- **Relationship (raw)**:\n```json")
        block.append(json.dumps(relationship, indent=2, ensure_ascii=False))
        block.append("```\n")
    else:
        block.append(f"- **Relationship (raw)**: {relationship}\n")

    if isinstance(edge_properties, dict):
        block.append("- **Edge Properties**:\n```json")
        block.append(json.dumps(edge_properties, indent=2, ensure_ascii=False))
        block.append("```\n")
    else:
        block.append(f"- **Edge Properties**: {edge_properties}\n")

    return block


def generate_markdown_report(data: dict[str, Any]) -> str:
    """根据边 Schema 数据生成 Markdown 报告。

    Args:
        data: 由 `generate_edge_schema_data` 生成的数据字典。

    Returns:
        str: 完整 Markdown 文本。
    """
    report: list[str] = []
    report.append("# Neo4j 边 Schema 参考\n")
    report.append(f"**生成时间**: {data['generated_at']}\n")
    report.append(f"**Neo4j 容器**: `{data['neo4j_container']}`\n")

    report.append("\n## 边示例（按 ID 前缀分类，每类一个完整示例）\n")
    if data["edge_examples_by_id_prefix"]:
        for row in data["edge_examples_by_id_prefix"]:
            prefix = row.get("edge_id_prefix", "other")
            report.extend(render_edge_example_block(row, f"{prefix}"))
    else:
        report.append("⚠️  无数据\n")

    report.append("\n## 关系示例（每个类型一个完整示例）\n")
    if data["edge_examples_by_type"]:
        for row in data["edge_examples_by_type"]:
            edge_type = row.get("edge_type", "Unknown")
            report.extend(render_edge_example_block(row, f"{edge_type}"))
    else:
        report.append("⚠️  无数据\n")

    report.append("\n## 关系示例（每个类型一个完整示例）\n")
    if data["edge_examples_by_type"]:
        table_rows = [
            "| 关系类型 | 源节点 | 源节点 ID | 目标节点 | 目标节点 ID |",
            "|----------|--------|-----------|----------|-------------|",
        ]
        for row in data["edge_examples_by_type"]:
            rel_type = row.get("edge_type", "")
            src_label = row.get("src_label", "")
            src_id = row.get("src_id", "")
            dst_label = row.get("dst_label", "")
            dst_id = row.get("dst_id", "")
            table_rows.append(f"| {rel_type} | {src_label} | {src_id} | {dst_label} | {dst_id} |")
        report.append("\n".join(table_rows))
        report.append("\n")
    else:
        report.append("⚠️  无数据\n")

    return "\n".join(report)


def main() -> int:
    """脚本主入口，解析参数并输出边 Schema 文档。

    Returns:
        int: 进程退出码。0 表示成功。
    """
    parser = argparse.ArgumentParser(description="Export Neo4j edge schema reference")
    parser.add_argument(
        "--format",
        choices=["md", "json"],
        default="md",
        help="输出格式 (default: md)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出文件路径 (default: memory_bench/docs/08_EDGE_SCHEMA_REFERENCE.*)",
    )
    parser.add_argument(
        "--container",
        default=NEO4J_CONTAINER,
        help=f"Neo4j 容器名 (default: {NEO4J_CONTAINER})",
    )
    args = parser.parse_args()

    log.info("Neo4j 边 Schema 导出工具")
    data = generate_edge_schema_data(container=args.container)

    if args.output:
        output_path = args.output
    else:
        docs_dir = Path(__file__).parent.parent / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        output_path = docs_dir / "08_EDGE_SCHEMA_REFERENCE"

    if args.format == "json":
        output_path = output_path.with_suffix(".json")
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info("JSON 已写入：%s", output_path)
    else:
        output_path = output_path.with_suffix(".md")
        report = generate_markdown_report(data)
        with output_path.open("w", encoding="utf-8") as f:
            f.write(report)
        log.info("Markdown 已写入：%s", output_path)

    log.info(
        "摘要：边示例（ID 前缀）=%d, 关系示例（关系类型）=%d",
        len(data["edge_examples_by_id_prefix"]),
        len(data["edge_examples_by_type"]),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""导出 Neo4j 图谱的完整 Schema（节点类型、属性、关系）。

用法：
    uv run memory_bench/scripts/export_schema.py
    uv run memory_bench/scripts/export_schema.py --format json
    uv run memory_bench/scripts/export_schema.py --output custom_path.md

自动读取 memory_bench/.env.benchmark 中的 Neo4j 配置：
- NEO4J_CONTAINER
- NEO4J_USER
- NEO4J_PASSWORD

输出：
- 默认：memory_bench/docs/06_SCHEMA_REFERENCE.md
- JSON 格式：memory_bench/docs/06_SCHEMA_REFERENCE.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from memory_bench.scripts.bench_logger import logger

log = logger.bind(group="export_schema")

try:
    from dotenv import load_dotenv
except ImportError:
    log.error("需要安装 python-dotenv")
    sys.exit(1)

# 加载 .env.benchmark
ENV_FILE = Path(__file__).parent.parent / ".env.benchmark"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
    log.info("已加载配置文件：%s", ENV_FILE)
else:
    log.warning("配置文件不存在：%s，使用默认值", ENV_FILE)

# Neo4j 配置（从环境变量读取）
NEO4J_CONTAINER = os.getenv("NEO4J_CONTAINER", "membench-neo4j-mem0")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4jneo4j")

log.info("Neo4j 配置：容器=%s, 用户=%s", NEO4J_CONTAINER, NEO4J_USER)

# Cypher 查询 - 简化版本
QUERY_NODE_LABELS = """
// 查询所有节点标签和数量
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS count
ORDER BY count DESC
"""

QUERY_ALL_NODES_BY_PREFIX = """
// 查询所有节点，按 ID 前缀分类（每个前缀一个示例）
MATCH (n)
WHERE n.id IS NOT NULL
WITH
  CASE
    WHEN n.id STARTS WITH "mem:" THEN "MemoryItem"
    WHEN n.id STARTS WITH "claim:" THEN "Claim"
    WHEN n.id STARTS WITH "topic:" THEN "Topic"
    WHEN n.id STARTS WITH "char:" THEN "Character"
    WHEN n.id STARTS WITH "user:" THEN "User"
    WHEN n.id STARTS WITH "agent:" THEN "Agent"
    WHEN n.id STARTS WITH "scene:" THEN "Scene"
    WHEN n.id STARTS WITH "conv:" THEN "Conversation"
    WHEN n.id STARTS WITH "dom:" THEN "Domain"
    WHEN n.id STARTS WITH "pred:" THEN "Predicate"
    ELSE "Other"
  END AS node_type,
  n
WITH node_type, collect(n)[0] AS example
RETURN
  node_type,
  example.id AS id,
  example.name AS name,
  example.display AS display,
  properties(example) AS all_props
ORDER BY node_type
"""

QUERY_ALL_EDGES_DEDUP = """
// 所有关系类型的去重示例（每个关系类型一个）
MATCH (n)-[r]->(m)
WITH type(r) AS relationship, n, m
ORDER BY relationship
WITH relationship, collect({from: n, to: m})[0] AS example
RETURN
  relationship,
  labels(example.from)[0] AS from_node,
  example.from.id AS from_id,
  labels(example.to)[0] AS to_node,
  example.to.id AS to_id
ORDER BY relationship
"""


def run_cypher(
    cypher_text: str,
    *,
    container: str = NEO4J_CONTAINER,
    user: str = NEO4J_USER,
    password: str = NEO4J_PASSWORD,
) -> tuple[bool, str]:
    """Pipe cypher_text into cypher-shell inside the Neo4j container."""
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
    """Split CSV line, handling nested braces {} and brackets [].

    Example: "a, b, {x: 1, y: 2}" → ["a", " b", " {x: 1, y: 2}"]
    """
    result = []
    current = []
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
            # End of field
            result.append("".join(current))
            current = []
        else:
            current.append(char)

    # Don't forget the last field
    if current:
        result.append("".join(current))

    return result


def convert_neo4j_map_to_json(neo4j_map: str) -> str:
    """Convert Neo4j Map format to valid JSON.

    Neo4j format: {name: "congyin", aliases: []}
    JSON format: {"name": "congyin", "aliases": []}
    """
    result = neo4j_map

    # Add quotes around unquoted keys
    result = re.sub(r"([{,]\s*)(\w+)(\s*:)", r'\1"\2"\3', result)

    # Replace single quotes with double quotes (if any)
    result = result.replace("'", '"')

    return result


def parse_cypher_output(output: str) -> list[dict[str, Any]]:
    """Parse cypher-shell plain format output into list of dicts.

    Handles CSV-like format where JSON fields may contain commas.
    Example:
    node_type, id, all_props
    "MemoryItem", "mem:xxx", {name: "test", data: "hello, world"}
    """
    lines = output.strip().split("\n")
    if len(lines) < 2:
        return []

    # First line is header
    headers = [h.strip().strip('"') for h in split_csv_line(lines[0])]
    rows = []

    for line in lines[1:]:
        if not line.strip():
            continue

        values = split_csv_line(line)
        if len(values) == len(headers):
            row_dict = {}
            for i, key in enumerate(headers):
                value = values[i].strip().strip('"')  # Also strip quotes from values
                # Try to parse JSON-like values
                if value.startswith("{") and value.endswith("}"):
                    try:
                        # Convert Neo4j Map format to JSON
                        json_str = convert_neo4j_map_to_json(value)
                        row_dict[key] = json.loads(json_str)
                    except (json.JSONDecodeError, ValueError):
                        row_dict[key] = value  # Keep as string if parsing fails
                else:
                    row_dict[key] = value
            rows.append(row_dict)

    return rows


def generate_schema_data(container: str) -> dict:
    """Generate schema data structure."""
    data = {
        "generated_at": datetime.now(UTC).astimezone().isoformat(),
        "neo4j_container": container,
        "node_examples": [],
        "edge_examples": [],
    }

    # 1. 所有节点按 ID 前缀分类示例
    log.info("查询节点示例（按 ID 前缀分类）...")
    ok, output = run_cypher(QUERY_ALL_NODES_BY_PREFIX, container=container)
    if ok:
        data["node_examples"] = parse_cypher_output(output)
        log.info("节点示例：%d 个", len(data["node_examples"]))
    else:
        log.error("节点示例查询失败：%s", output)

    # 2. 所有关系类型的去重示例
    log.info("查询关系示例...")
    ok, output = run_cypher(QUERY_ALL_EDGES_DEDUP, container=container)
    if ok:
        data["edge_examples"] = parse_cypher_output(output)
        log.info("关系示例：%d 个", len(data["edge_examples"]))
    else:
        log.error("关系示例查询失败：%s", output)

    return data


def generate_markdown_report(data: dict) -> str:
    """Generate Markdown report from schema data."""
    report = []
    report.append("# Neo4j 图谱 Schema 参考\n")
    report.append(f"**生成时间**: {data['generated_at']}\n")
    report.append(f"**Neo4j 容器**: `{data['neo4j_container']}`\n")

    # 1. 节点示例（按 ID 前缀分类）
    report.append("\n## 节点示例（按 ID 前缀分类，每类一个完整示例）\n")
    if data["node_examples"]:
        for row in data["node_examples"]:
            node_type = row.get("node_type", "")
            node_id = row.get("id", "")
            name = row.get("name", "")
            display = row.get("display", "")
            all_props = row.get("all_props", "")
            report.append(f"\n### {node_type}\n")
            report.append(f"- **ID**: {node_id}\n")
            report.append(f"- **Name**: {name}\n")
            report.append(f"- **Display**: {display}\n")
            if isinstance(all_props, dict):
                props_json = json.dumps(all_props, indent=2, ensure_ascii=False)
                report.append(f"- **Properties**:\n```json\n{props_json}\n```\n")
            else:
                report.append(f"- **Properties**: {all_props}\n")
    else:
        report.append("⚠️  无数据\n")

    # 2. 关系示例（每个类型一个）
    report.append("\n## 关系示例（每个类型一个完整示例）\n")
    if data["edge_examples"]:
        # Build table rows without extra newlines
        table_rows = []
        table_rows.append("| 关系类型 | 源节点 | 源节点 ID | 目标节点 | 目标节点 ID |")
        table_rows.append("|----------|--------|-----------|----------|-------------|")
        for row in data["edge_examples"]:
            rel_type = row.get("relationship", "")
            from_node = row.get("from_node", "")
            from_id = row.get("from_id", "")
            to_node = row.get("to_node", "")
            to_id = row.get("to_id", "")
            table_rows.append(f"| {rel_type} | {from_node} | {from_id} | {to_node} | {to_id} |")
        report.append("\n".join(table_rows))
        report.append("\n")
    else:
        report.append("⚠️  无数据\n")

    return "\n".join(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Neo4j schema reference")
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
        help="输出文件路径 (default: memory_bench/docs/06_SCHEMA_REFERENCE.*)",
    )
    parser.add_argument(
        "--container",
        default=NEO4J_CONTAINER,
        help=f"Neo4j 容器名 (default: {NEO4J_CONTAINER})",
    )
    args = parser.parse_args()

    container = args.container

    log.info("Neo4j 图谱 Schema 导出工具")

    # 生成 schema 数据
    data = generate_schema_data(container=container)

    # 确定输出路径
    if args.output:
        output_path = args.output
    else:
        docs_dir = Path(__file__).parent.parent / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        if args.format == "json":
            output_path = docs_dir / "06_SCHEMA_REFERENCE.json"
        else:
            output_path = docs_dir / "06_SCHEMA_REFERENCE.md"

    # 写入文件
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

    # 打印摘要
    log.info("摘要：节点示例=%d, 关系示例=%d", len(data["node_examples"]), len(data["edge_examples"]))

    return 0


if __name__ == "__main__":
    sys.exit(main())

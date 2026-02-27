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
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

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

QUERY_ALL_NODE_EXAMPLES = """
// 每个节点标签查询一个完整示例
MATCH (n)
WITH labels(n) AS node_labels, n
WHERE size(node_labels) > 0
WITH node_labels[0] AS label, n
ORDER BY label
WITH label, collect(n) AS nodes
WITH label, nodes[0] AS example
RETURN 
  label,
  example.id AS id,
  example.name AS name,
  example.display AS display,
  toString(properties(example)) AS all_props
ORDER BY label
"""

QUERY_ALL_EDGES_DEDUP = """
// 所有关系类型的去重示例（每个关系类型一个）
MATCH (n)-[r]->(m)
RETURN 
  labels(n)[0] AS from_node, 
  n.id AS from_id, 
  type(r) AS relationship, 
  labels(m)[0] AS to_node, 
  m.id AS to_id
ORDER BY type(r)
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


def parse_cypher_output(output: str) -> list[dict[str, str]]:
    """Parse cypher-shell plain format output into list of dicts.
    
    Supports both CSV format (comma-separated) and table format (pipe-separated).
    """
    lines = output.strip().split("\n")
    if len(lines) < 1:
        return []

    # Detect format: CSV (comma-separated) or table (pipe-separated)
    first_line = lines[0]
    is_csv = "," in first_line and "|" not in first_line
    
    if is_csv:
        # CSV format: parse as CSV
        reader = csv.DictReader(StringIO(output))
        # Strip whitespace from keys and values
        rows = []
        for row in reader:
            cleaned_row = {}
            for k, v in row.items():
                key = k.strip() if k else ""
                value = v.strip() if isinstance(v, str) and v else (v if v is not None else "")
                cleaned_row[key] = value
            rows.append(cleaned_row)
        return rows
    
    # Table format (pipe-separated) - not used in this simplified version
    return []


def generate_schema_data(container: str) -> dict:
    """Generate schema data structure."""
    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "neo4j_container": container,
        "node_labels": [],
        "node_examples": [],
        "edge_examples": [],
    }

    # 1. 节点标签和数量
    log.info("查询节点标签...")
    ok, output = run_cypher(QUERY_NODE_LABELS, container=container)
    if ok:
        data["node_labels"] = parse_cypher_output(output)
        log.info("节点标签：%d 个", len(data["node_labels"]))
    else:
        log.error("节点标签查询失败：%s", output)

    # 2. 每个节点标签的完整示例
    log.info("查询节点示例...")
    ok, output = run_cypher(QUERY_ALL_NODE_EXAMPLES, container=container)
    if ok:
        data["node_examples"] = parse_cypher_output(output)
        log.info("节点示例：%d 个", len(data["node_examples"]))
    else:
        log.error("节点示例查询失败：%s", output)

    # 3. 所有关系类型的去重示例
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

    # 1. 节点类型
    report.append("\n## 一、节点类型（Node Labels）\n")
    if data["node_labels"]:
        report.append("| 节点类型 | 数量 |\n")
        report.append("|----------|------|\n")
        for row in data["node_labels"]:
            label = row.get("label", "")
            count = row.get("count", "")
            report.append(f"| `{label}` | {count} |\n")
    else:
        report.append("⚠️  无数据\n")

    # 2. 节点示例（每个标签一个）
    report.append("\n## 二、节点示例（每个类型一个完整示例）\n")
    if data["node_examples"]:
        for row in data["node_examples"]:
            label = row.get("label", "")
            node_id = row.get("id", "")
            name = row.get("name", "")
            display = row.get("display", "")
            all_props = row.get("all_props", "")
            report.append(f"\n### `{label}`\n")
            report.append(f"- **ID**: `{node_id}`\n")
            report.append(f"- **Name**: `{name}`\n")
            report.append(f"- **Display**: `{display}`\n")
            report.append(f"- **Properties**: `{all_props}`\n")
    else:
        report.append("⚠️  无数据\n")

    # 3. 关系示例（每个类型一个）
    report.append("\n## 三、关系示例（每个类型一个完整示例）\n")
    if data["edge_examples"]:
        report.append("| 关系类型 | 源节点 | 源节点 ID | 目标节点 | 目标节点 ID |\n")
        report.append("|----------|--------|-----------|----------|-------------|\n")
        for row in data["edge_examples"]:
            rel_type = row.get("relationship", "")
            from_node = row.get("from_node", "")
            from_id = row.get("from_id", "")
            to_node = row.get("to_node", "")
            to_id = row.get("to_id", "")
            report.append(f"| `{rel_type}` | `{from_node}` | `{from_id}` | `{to_node}` | `{to_id}` |\n")
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
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info("JSON 已写入：%s", output_path)
    else:
        output_path = output_path.with_suffix(".md")
        report = generate_markdown_report(data)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        log.info("Markdown 已写入：%s", output_path)

    # 打印摘要
    log.info("摘要：节点类型=%d, 节点示例=%d, 关系示例=%d",
             len(data["node_labels"]), len(data["node_examples"]), len(data["edge_examples"]))

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""导出 Neo4j 图谱的边（Edge）Schema 参考文档。

用法：
    uv run memory_bench/scripts/export_edge_schema.py
    uv run memory_bench/scripts/export_edge_schema.py --output custom_path.md

自动读取 memory_bench/.env.benchmark 中的 Neo4j 配置：
- NEO4J_CONTAINER
- NEO4J_USER
- NEO4J_PASSWORD

输出：
- 默认：memory_bench/docs/08_EDGE_SCHEMA_REFERENCE.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

from memory_bench.scripts.bench_logger import logger

log = logger.bind(group="export_edge_schema")

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

# Cypher 查询
QUERY_EDGE_WITH_PROPERTIES = """
// 查询边的完整信息（源节点、目标节点、属性）
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


def parse_cypher_output(output: str) -> list[dict[str, Any]]:
    """Parse cypher-shell plain format output into list of dicts.

    Handles CSV-like format where JSON fields may contain commas.
    """
    lines = output.strip().split("\n")
    if len(lines) < 1:
        return []

    # Detect format: CSV (comma-separated) or table (pipe-separated)
    first_line = lines[0]
    is_csv = "," in first_line and "|" not in first_line

    if is_csv:
        # CSV format: parse as CSV
        reader = StringIO(output)
        import csv

        rows = []
        for row in csv.DictReader(reader):
            cleaned_row = {}
            for k, v in row.items():
                key = k.strip() if k else ""
                if v is None:
                    value = ""
                elif isinstance(v, str):
                    value = v.strip()
                    # Try to parse JSON-like values
                    if value.startswith("{") and value.endswith("}"):
                        try:
                            cleaned_value = value.replace("'", '"')
                            cleaned_row[key] = json.loads(cleaned_value)
                            continue
                        except (json.JSONDecodeError, ValueError):
                            pass
                else:
                    value = str(v)
                cleaned_row[key] = value
            rows.append(cleaned_row)
        return rows

    # Table format (pipe-separated) - not used in this simplified version
    return []


def generate_markdown_report(edge_properties: list[dict[str, Any]]) -> str:
    """Generate Markdown report from edge properties data."""
    report = []
    report.append("# Neo4j 图谱边 Schema 参考\n")
    report.append(f"**生成时间**: {datetime.now(UTC).isoformat()}\n")
    report.append(f"**Neo4j 容器**: `{NEO4J_CONTAINER}`\n")

    # 边属性详情（每个类型一个完整示例）
    report.append("\n## 边属性详情（每个类型一个完整示例）\n")
    if edge_properties:
        for row in edge_properties:
            edge_type = row.get("edge_type", "")
            src_label = row.get("src_label", "")
            src_id = row.get("src_id", "")
            dst_label = row.get("dst_label", "")
            dst_id = row.get("dst_id", "")
            edge_props = row.get("edge_properties", {})

            # 标题：EDGE_TYPE (src_id --> dst_id)
            report.append(f"\n### {edge_type} ({src_id} → {dst_id})\n")

            # 属性表格
            if isinstance(edge_props, dict):
                report.append("| Property | Value |\n")
                report.append("|----------|-------|\n")
                for key, value in sorted(edge_props.items()):
                    # 格式化 value，避免过长
                    if isinstance(value, str) and len(value) > 100:
                        value = value[:100] + "..."
                    report.append(f"| `{key}` | {value} |\n")
                report.append("\n")
            else:
                report.append(f"**Properties**: {edge_props}\n\n")
    else:
        report.append("⚠️  无数据\n")

    return "\n".join(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Neo4j edge schema reference")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出文件路径 (default: memory_bench/docs/08_EDGE_SCHEMA_REFERENCE.md)",
    )
    parser.add_argument(
        "--container",
        default=NEO4J_CONTAINER,
        help=f"Neo4j 容器名 (default: {NEO4J_CONTAINER})",
    )
    args = parser.parse_args()

    container = args.container

    log.info("Neo4j 图谱边 Schema 导出工具")

    # 查询边的完整信息（带属性）
    log.info("查询边属性...")
    ok, output = run_cypher(QUERY_EDGE_WITH_PROPERTIES, container=container)
    if not ok:
        log.error("边属性查询失败：%s", output)
        return 1

    edge_properties = parse_cypher_output(output)
    log.info("边属性：%d 个", len(edge_properties))

    # 确定输出路径
    if args.output:
        output_path = args.output
    else:
        docs_dir = Path(__file__).parent.parent / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        output_path = docs_dir / "08_EDGE_SCHEMA_REFERENCE.md"

    # 生成 Markdown 报告
    report = generate_markdown_report(edge_properties)

    # 写入文件
    output_path = output_path.with_suffix(".md")
    with output_path.open("w", encoding="utf-8") as f:
        f.write(report)
    log.info("Markdown 已写入：%s", output_path)

    # 打印摘要
    log.info("摘要：边属性=%d", len(edge_properties))

    return 0


if __name__ == "__main__":
    sys.exit(main())

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
import subprocess
import sys
from datetime import datetime, timezone
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

# Cypher 查询
QUERY_NODE_LABELS = """
// 查询所有节点标签和数量
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS count
ORDER BY count DESC
"""

QUERY_NODE_PROPERTIES = """
// 查询每个标签的所有属性
MATCH (n)
UNWIND labels(n) AS label
WITH label, n
RETURN label, keys(n) AS properties, count(*) AS count
ORDER BY count DESC
"""

QUERY_RELATIONSHIPS = """
// 查询所有关系类型和数量
MATCH ()-[r]->()
RETURN type(r) AS relationship_type, count(*) AS count
ORDER BY count DESC
"""

QUERY_RELATIONSHIP_STRUCTURE = """
// 查询关系的完整结构（源节点类型 → 目标节点类型）
MATCH (n)-[r]->(m)
WITH type(r) AS rel_type, labels(n)[0] AS from_label, labels(m)[0] AS to_label, count(*) AS count
RETURN rel_type, from_label, to_label, count
ORDER BY rel_type
"""

QUERY_EXAMPLE_NODES = """
// 每个标签查询一个示例节点
MATCH (n)
WITH labels(n)[0] AS label, n
ORDER BY label
WITH label, collect(DISTINCT {id: n.id, name: n.name, display: n.display, props: properties(n)})[0..3] AS examples
RETURN label, examples
ORDER BY label
"""

# 规范文档（静态部分）
SPECIFICATION = """
## 六、规范（Specification）

### 6.1 节点 ID 格式

所有节点必须有 `id` 属性，格式为 `{type}:{value}`：

| 节点类型 | ID 前缀 | 示例 |
|----------|--------|------|
| MemoryItem | `mem:` | `mem:078b383a19bf...` (SHA256 前 12 位) |
| User | `user:` | `user:xnne` |
| Agent | `agent:` | `agent:congyin` |
| Scene | `scene:` | `scene:chill_ai_chat` |
| Character | `char:` | `char:congyin`, `char:xnne` |
| Conversation | `conv:` | `conv:ch01` (离线), `conv:2026-02-27` (实时) |

### 6.2 必需属性

所有节点必须有：
- `id` (string) - 唯一标识符
- `labels` (list) - 节点类型标签（单元素列表）

推荐属性：
- `name` (string) - 显示名称
- `display` (string) - 简短显示文本

### 6.3 关系方向

所有关系都有固定方向：

```
Character -OWNS_MEMORY→ MemoryItem
MemoryItem -FROM_CONV→ Conversation
MemoryItem -IN_SCENE→ Scene
MemoryItem -HAS_CHARACTER→ Character
Conversation -CONV_IN_SCENE→ Scene
Conversation -CONV_HAS_CHARACTER→ Character
User -USER_IN_SCENE→ Scene
Agent -ACTOR→ Character
Character -IN_SCENE→ Scene
```

### 6.4 离线管线 vs 实时管线

| 特性 | 离线管线 | 实时管线 |
|------|----------|----------|
| Conversation ID | `conv:ch01`, `conv:ch02` (按章节) | `conv:2026-02-27` (按日期) |
| MemoryItem ID | `mem:<hash>` (来自 mem0 export) | `mem:<hash>` (SHA256 前 12 位) |
| Character ID | `char:congyin`, `char:xnne` | `char:congyin`, `char:xnne` |
| 触发方式 | 批量处理 (just mem0-run-*) | 实时对话 (memory-chat-server) |

**重要**：两个管线的 Schema 必须完全一致，才能合并到同一个图谱中！
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
    """Parse cypher-shell plain format output into list of dicts."""
    lines = output.strip().split("\n")
    if len(lines) < 2:
        return []

    # First line is header
    headers = [h.strip() for h in lines[0].split("|")]
    rows = []

    for line in lines[2:]:  # Skip header and separator line
        if not line.strip():
            continue
        # Split by | and strip whitespace
        values = [v.strip() for v in line.split("|")]
        if len(values) == len(headers):
            rows.append(dict(zip(headers, values)))

    return rows


def generate_schema_data(container: str) -> dict:
    """Generate schema data structure."""
    data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "neo4j_container": container,
        "node_labels": [],
        "node_properties": [],
        "relationships": [],
        "relationship_structure": [],
        "example_nodes": [],
    }

    # 1. 节点标签
    log.info("查询节点标签...")
    ok, output = run_cypher(QUERY_NODE_LABELS, container=container)
    if ok:
        data["node_labels"] = parse_cypher_output(output)
    else:
        log.error("节点标签查询失败：%s", output)

    # 2. 节点属性
    log.info("查询节点属性...")
    ok, output = run_cypher(QUERY_NODE_PROPERTIES, container=container)
    if ok:
        data["node_properties"] = parse_cypher_output(output)
    else:
        log.error("节点属性查询失败：%s", output)

    # 3. 关系类型
    log.info("查询关系类型...")
    ok, output = run_cypher(QUERY_RELATIONSHIPS, container=container)
    if ok:
        data["relationships"] = parse_cypher_output(output)
    else:
        log.error("关系类型查询失败：%s", output)

    # 4. 关系结构
    log.info("查询关系结构...")
    ok, output = run_cypher(QUERY_RELATIONSHIP_STRUCTURE, container=container)
    if ok:
        data["relationship_structure"] = parse_cypher_output(output)
    else:
        log.error("关系结构查询失败：%s", output)

    # 5. 示例节点
    log.info("查询示例节点...")
    ok, output = run_cypher(QUERY_EXAMPLE_NODES, container=container)
    if ok:
        data["example_nodes"] = parse_cypher_output(output)
    else:
        log.error("示例节点查询失败：%s", output)

    return data


def generate_markdown_report(data: dict) -> str:
    """Generate Markdown report from schema data."""
    report = []
    report.append("# Neo4j 图谱 Schema 参考\n")
    report.append(f"**生成时间**: {data['generated_at']}\n")
    report.append(f"**Neo4j 容器**: `{data['neo4j_container']}`\n")

    # 1. 节点标签
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

    # 2. 节点属性
    report.append("\n## 二、节点属性（Node Properties）\n")
    if data["node_properties"]:
        for row in data["node_properties"]:
            label = row.get("label", "")
            props = row.get("properties", "")
            count = row.get("count", "")
            report.append(f"\n### `{label}` ({count} 个节点)\n")
            report.append(f"**属性**: `{props}`\n")
    else:
        report.append("⚠️  无数据\n")

    # 3. 关系类型
    report.append("\n## 三、关系类型（Relationship Types）\n")
    if data["relationships"]:
        report.append("| 关系类型 | 数量 |\n")
        report.append("|----------|------|\n")
        for row in data["relationships"]:
            rel_type = row.get("relationship_type", "")
            count = row.get("count", "")
            report.append(f"| `{rel_type}` | {count} |\n")
    else:
        report.append("⚠️  无数据\n")

    # 4. 关系结构
    report.append("\n## 四、关系结构（Relationship Structure）\n")
    if data["relationship_structure"]:
        report.append("| 关系类型 | 源节点类型 | 目标节点类型 | 数量 |\n")
        report.append("|----------|------------|--------------|------|\n")
        for row in data["relationship_structure"]:
            rel_type = row.get("rel_type", "")
            from_label = row.get("from_label", "")
            to_label = row.get("to_label", "")
            count = row.get("count", "")
            report.append(f"| `{rel_type}` | `{from_label}` | `{to_label}` | {count} |\n")
    else:
        report.append("⚠️  无数据\n")

    # 5. 示例节点
    report.append("\n## 五、示例节点（Example Nodes）\n")
    if data["example_nodes"]:
        for row in data["example_nodes"]:
            label = row.get("label", "")
            examples = row.get("examples", "")
            report.append(f"\n### `{label}`\n")
            report.append(f"```\n{examples}\n```\n")
    else:
        report.append("⚠️  无数据\n")

    # 6. 规范
    report.append(SPECIFICATION)

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
    log.info("摘要：节点类型=%d, 关系类型=%d, 关系结构=%d",
             len(data['node_labels']), len(data['relationships']), len(data['relationship_structure']))

    return 0


if __name__ == "__main__":
    sys.exit(main())

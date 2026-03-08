# export_node_schema.py

## 作用

导出 Neo4j 图谱的完整 Schema 参考文档，包括节点示例和关系示例。

## 调用示例

```bash
# 导出 Markdown 格式（默认）
uv run memory_bench/scripts/export_node_schema.py

# 导出 JSON 格式
uv run memory_bench/scripts/export_node_schema.py --format json

# 自定义输出路径
uv run memory_bench/scripts/export_node_schema.py --output /tmp/schema.md

# 指定 Neo4j 容器
uv run memory_bench/scripts/export_node_schema.py --container my-neo4j-container
```

## 输入

- **Neo4j 容器**：从 `.env.benchmark` 读取 `NEO4J_CONTAINER`（默认：`membench-neo4j-mem0`）
- **认证信息**：从 `.env.benchmark` 读取 `NEO4J_USER` 和 `NEO4J_PASSWORD`

## 输出

- **Markdown 格式**：`memory_bench/docs/06_NODE_SCHEMA_REFERENCE.md`
- **JSON 格式**：结构化 JSON 文件

## 节点分类规则

脚本根据节点 ID 的前缀自动分类：

| ID 前缀 | 节点类型 |
|---------|---------|
| `mem:` | MemoryItem |
| `claim:` | Claim |
| `topic:` | Topic |
| `char:` | Character |
| `user:` | User |
| `agent:` | Agent |
| `scene:` | Scene |
| `conv:` | Conversation |
| `dom:` | Domain |
| `pred:` | Predicate |
| 其他 | Other |

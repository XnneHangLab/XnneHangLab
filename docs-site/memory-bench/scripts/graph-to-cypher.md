# graph_to_cypher.py

## 作用

将 mem0_to_graph / claims_to_graph 输出的 nodes/edges JSONL 转为 Neo4j 导入用的 cypher 脚本。

## 调用示例

```bash
uv run memory_bench/scripts/graph_to_cypher.py \
  --nodes memory_bench/logs/replay_mem0/graphify/graph_nodes_*.jsonl \
  --edges memory_bench/logs/replay_mem0/graphify/graph_edges_*.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify/neo4j \
  --prefix graph
```

## 参数

| 参数 | 说明 |
|------|------|
| `--nodes`（必填） | graph_nodes JSONL 路径 |
| `--edges`（必填） | graph_edges JSONL 路径 |
| `--out-dir`（必填） | 输出目录 |
| `--prefix` | 输出文件名前缀（默认 `graph`） |
| `--dry-run` | 只解析统计 |

## 输出

- `<prefix>_constraints.cypher`
- `<prefix>_import.cypher`
- `<prefix>_report.json`

# neo4j_apply_cypher.py

## 作用

将 cypher 文件一键导入指定 Neo4j docker 容器。

## 目标实例

- `mem0`
- `zep`
- `cognee`

## 调用示例

```bash
uv run memory_bench/scripts/neo4j_apply_cypher.py mem0 \
  --constraints path/to/graph_constraints_*.cypher \
  --import-file path/to/graph_import_*.cypher

uv run memory_bench/scripts/neo4j_apply_cypher.py mem0 \
  --constraints path/to/constraints.cypher \
  --import-file path/to/import.cypher \
  --dry-run
```

## 参数

| 参数 | 说明 |
|------|------|
| 位置参数 | 目标实例：`mem0` / `zep` / `cognee` |
| `--constraints`（必填） | constraints cypher 文件路径 |
| `--import-file`（必填） | import cypher 文件路径 |
| `--dry-run` | 只打印命令，不执行 |

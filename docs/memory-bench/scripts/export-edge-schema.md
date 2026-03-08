# export_edge_schema.py

## 作用

导出 Neo4j 图谱中"边"的完整示例文档，分别按 **边 ID 前缀** 和 **关系类型** 去重保留每类一个示例。

## 调用示例

```bash
# 导出 Markdown 格式（默认）
uv run memory_bench/scripts/export_edge_schema.py

# 导出 JSON 格式
uv run memory_bench/scripts/export_edge_schema.py --format json

# 自定义输出路径
uv run memory_bench/scripts/export_edge_schema.py --output /tmp/edge-schema.md

# 指定 Neo4j 容器
uv run memory_bench/scripts/export_edge_schema.py --container my-neo4j-container
```

## 输出结构

Markdown 文档包含两个章节：

1. `## 边示例（按 ID 前缀分类，每类一个完整示例）`
2. `## 关系示例（每个类型一个完整示例）`

其中每条示例都包含：
- `Edge Type`
- `Source`（src label + src id）
- `Target`（dst label + dst id）
- `Relationship (raw)`（Neo4j relationship 完整对象）
- `Edge Properties`（`properties(r)` 结果）

## 去重规则

- **按边 ID 前缀**：基于 `r.id` 的 `:` 前缀分组，每组仅保留一个完整样例
- **按关系类型**：基于 `type(r)` 分组，每种关系仅保留一个完整样例

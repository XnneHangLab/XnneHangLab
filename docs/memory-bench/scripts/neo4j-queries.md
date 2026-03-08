# neo4j_queries.py

## 作用

Neo4j Cypher 查询模板模块，与业务逻辑分离。

将所有 Cypher 语句从 `router.py` / `graph_writer.py` 移出，集中管理。

## 内容

- 节点 MERGE 模板
- 边 MERGE 模板
- 约束创建语句
- 查询模板

## 使用方式

```python
from memory_bench.server.neo4j_queries import (
    build_node_merge,
    build_edge_merge,
    CONSTRAINTS_CYPER,
)

cypher = build_node_merge("MemoryItem", {"id": "mem:xxx", "name": "..."})
```

## 设计决策

- **职责分离**：Cypher 语句与业务逻辑解耦
- **易于维护**：修改 Cypher 只需改一个文件
- **可测试**：独立测试 Cypher 模板

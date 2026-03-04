# graph_writer.py

## 作用

实时图谱写入模块，是离线管线 `claims_to_graph.py` → `graph_to_cypher.py` → `neo4j_apply_cypher.py` 的实时对应物。

接收 claim records，在内存中完成 Graph IR 构建 + Cypher 生成，直接通过 `docker exec cypher-shell` 写入 Neo4j。

## 核心函数

| 函数 | 说明 |
|------|------|
| `write_to_neo4j()` | 主入口：records → split → build_graph → Cypher → docker exec |
| `_run_cypher()` | 将 Cypher 文本管道到 `docker exec cypher-shell` |
| `_ensure_constraints()` | 幂等创建 `Node.id` 唯一约束 |
| `_docker_available()` | 检查 docker CLI 是否在 PATH 上 |

## 返回值

`WriteResult` dataclass：

| 字段 | 类型 | 说明 |
|------|------|------|
| `nodes_written` | int | 成功执行的 node MERGE 数 |
| `edges_written` | int | 成功执行的 edge MERGE 数 |
| `cypher_ok` | bool | docker exec 是否成功 |
| `error` | str | 失败时的错误信息 |

## 设计决策

- **复用离线模块**：构图和 Cypher 生成逻辑零重复
- **同执行路径**：与 `neo4j_apply_cypher.py` 一样用 `docker exec`
- **优雅降级**：Docker 不可用 / Neo4j 挂了 → 记日志 + 返回

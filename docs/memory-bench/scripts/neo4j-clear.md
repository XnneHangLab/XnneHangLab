# neo4j_clear.py

## 作用

清空 Neo4j 图数据（所有节点和关系），无需重启容器。

相比 `clean-and-restart-neo4j`（删除 volume + 重启容器），此脚本：
- **更快**：无需 sleep 等待容器重启（节省 20-30 秒）
- **更温和**：只清空数据，保留容器状态和配置
- **支持多容器**：可通过 `--container` 指定目标 Neo4j 实例

## 调用示例

```bash
# 清空默认容器（mem0）
uv run memory_bench/scripts/neo4j_clear.py

# 清空其他容器
uv run memory_bench/scripts/neo4j_clear.py --container membench-neo4j-zep

# 保留 constraints/indexes
uv run memory_bench/scripts/neo4j_clear.py --keep-constraints

# 预演（不执行，只显示会运行的命令）
uv run memory_bench/scripts/neo4j_clear.py --dry-run
```

## 参数

| 参数 | 说明 |
|------|------|
| `--container` | Neo4j Docker 容器名（默认：`membench-neo4j-mem0`） |
| `--user` | Neo4j 用户名（默认：`neo4j`） |
| `--password` | Neo4j 密码（默认：`neo4jneo4j`） |
| `--keep-constraints` | 保留现有 constraints 和 indexes |
| `--dry-run` | 只打印命令，不执行 |

## 环境变量

从 `memory_bench/.env.benchmark` 读取（可选）：

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `NEO4J_CONTAINER` | Neo4j 容器名 | `membench-neo4j-mem0` |
| `NEO4J_USER` | Neo4j 用户名 | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 密码 | `neo4jneo4j` |

**优先级**：CLI 参数 > 环境变量 > 脚本默认值。

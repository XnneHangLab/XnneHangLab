# Neo4j 本地部署与脚本接入说明

本文说明如何在本地运行 Neo4j，并使用 `replay_graphiti.py` / `probe_graphiti.py` 进行写入与查询。

## 1. 依赖准备

在仓库根目录执行：

```bash
uv sync --group memory_bench
```

> 该组包含 `neo4j` Python 驱动（用于脚本连接 Bolt）。

---

## 2. 启动 Neo4j（本地）

可任选一种方式：

### 2.1 方式 A：本机安装 Neo4j Community

- 下载并安装 Neo4j Community（5.x 建议）。
- 启动后确认：
  - Bolt: `bolt://localhost:7687`
  - Browser: `http://localhost:7474`
- 首次登录时设置 `neo4j` 用户密码（并同步到环境变量）。

### 2.2 方式 B：容器方式（若本机有 Docker）

```bash
docker run --name membench-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/neo4jneo4j \
  -d neo4j:5
```


### 2.3 方式 C：Docker Compose（推荐）

如果你更习惯 `docker compose`，可参考：

- https://calpa.me/blog/how-to-create-neo4j-database-using-docker-and-docker-compose/

仓库已提供可直接使用的 Compose 文件：`memory_bench/docker-compose.neo4j.yml`。

如需自定义，可参考下方最小示例：

```yaml
services:
  neo4j:
    image: neo4j:5
    container_name: membench-neo4j
    restart: unless-stopped
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/neo4jneo4j
    volumes:
      - ./neo4j/data:/data
      - ./neo4j/logs:/logs
```

启动（使用仓库内 compose 文件）：

```bash
docker compose -f memory_bench/docker-compose.neo4j.yml up -d
```

---

## 3. 环境变量配置

建议在 shell 或 `.env` 中设置：

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=neo4jneo4j
export NEO4J_DATABASE=neo4j
```

---

## 4. 回放写入图谱

> 前置要求：请先确保 Neo4j 实例可访问（Bolt `7687` / Browser `7474`）。

```bash
uv run python memory_bench/scripts/replay_graphiti.py \
  --backend neo4j \
  --memory-system mem0 \
  --input memory_bench/data/events/compiled/all.jsonl \
  --clear
```

常用参数：

- `--skip-role ui,tool`
- `--skip-tags filler`
- `--only-tags canon_only,episodic,probe`
- `--dry-run`（只做转换统计，不连接数据库）

---

## 5. probe 查询图谱

> 前置要求：probe 仅查询已有图谱，不会自动启动 Neo4j；请先完成上面的部署与回放。

### 5.1 单条查询

```bash
uv run python memory_bench/scripts/probe_graphiti.py \
  --backend neo4j \
  --memory-system mem0 \
  --query "她最担心什么" \
  --character-id elaina
```

### 5.2 使用 probe 事件文件批量查询

```bash
uv run python memory_bench/scripts/probe_graphiti.py \
  --probes-jsonl memory_bench/data/events/compiled/all.jsonl \
  --output memory_bench/logs/probe_graphiti/probe_results.jsonl
```

---

## 6. 多后端扩展说明

当前图谱后端仅支持 `neo4j`。

同时可用 `--memory-system mem0|zep|cognee` 隔离图谱存储；默认会映射到独立图数据库（例如 `mem0_graph` / `zep_graph` / `cognee_graph`），也可通过 `--graph-name` 显式覆盖。

---

## 7. Neo4j Browser 可视化建议

打开 `http://localhost:7474` 后可执行：

```cypher
MATCH (n)
RETURN n
LIMIT 200
```

以及更聚焦的查询：

```cypher
MATCH (c:Character)-[:OWNS_CONVERSATION]->(v:Conversation)<-[:IN_CONVERSATION]-(u:Utterance)
RETURN c,v,u
LIMIT 200
```

```cypher
MATCH (u:Utterance)-[:MENTIONS_FACT]->(f:CanonFact)
RETURN u,f
LIMIT 200
```

```cypher
MATCH (u:Utterance)-[:AS_EPISODE]->(e:EpisodicEvent)
RETURN u,e
LIMIT 200
```

以上三组查询可直接体现角色、场景、对话、稳定事实与 episodic 事件关系。

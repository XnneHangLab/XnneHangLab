# Neo4j 本地部署与脚本接入说明

本文说明如何在本地运行 Neo4j，并使用 `replay_graphiti.py` / `probe_graphiti.py` 进行写入与查询。

## 1. 依赖准备

在仓库根目录执行：

```bash
uv sync --group memory_bench
```

> 该组包含 `neo4j` Python 驱动（用于脚本连接 Bolt）。

---

## 2. 启动 Neo4j（推荐：Docker Compose 三实例）

我们使用 Neo4j 社区版，建议采用**三容器隔离**方式，分别承载 `mem0/zep/cognee`。

可参考：

- https://calpa.me/blog/how-to-create-neo4j-database-using-docker-and-docker-compose/

仓库已提供 Compose 文件：`memory_bench/docker-compose.neo4j.yml`。

端口规划：

- `neo4j_mem0`: Browser `7474`, Bolt `7687`
- `neo4j_zep`: Browser `7475`, Bolt `7688`
- `neo4j_cognee`: Browser `7476`, Bolt `7689`

数据目录隔离：

- `./neo4j-data/mem0/...`
- `./neo4j-data/zep/...`
- `./neo4j-data/cognee/...`

> 如果你希望完全落到 D 盘，直接把 compose 里的挂载路径改成绝对路径，例如 `D:/membench/neo4j-data/mem0/data:/data`。

启动命令：

```bash
docker compose -f memory_bench/docker-compose.neo4j.yml up -d
```

---

## 3. 环境变量配置（可选）

```bash
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=neo4jneo4j
export NEO4J_DATABASE=neo4j

# 可选：按 memory_system 自动匹配 URI
export NEO4J_URI_MEM0=bolt://127.0.0.1:7687
export NEO4J_URI_ZEP=bolt://127.0.0.1:7688
export NEO4J_URI_COGNEE=bolt://127.0.0.1:7689
```

---

## 4. 回放写入图谱

> 前置要求：请先确保 Neo4j 实例可访问（Bolt 7687/7688/7689）。

### 4.1 mem0（7687）

```bash
uv run python memory_bench/scripts/replay_graphiti.py \
  --backend neo4j \
  --memory-system mem0 \
  --neo4j-uri bolt://127.0.0.1:7687 \
  --database neo4j \
  --input memory_bench/data/events/compiled/all.jsonl \
  --clear
```

### 4.2 zep（7688）

```bash
uv run python memory_bench/scripts/replay_graphiti.py \
  --backend neo4j \
  --memory-system zep \
  --neo4j-uri bolt://127.0.0.1:7688 \
  --database neo4j \
  --input memory_bench/data/events/compiled/all.jsonl \
  --clear
```

### 4.3 cognee（7689）

```bash
uv run python memory_bench/scripts/replay_graphiti.py \
  --backend neo4j \
  --memory-system cognee \
  --neo4j-uri bolt://127.0.0.1:7689 \
  --database neo4j \
  --input memory_bench/data/events/compiled/all.jsonl \
  --clear
```

---

## 5. probe 查询图谱

### 5.1 mem0（7687）

```bash
uv run python memory_bench/scripts/probe_graphiti.py \
  --backend neo4j \
  --memory-system mem0 \
  --neo4j-uri bolt://127.0.0.1:7687 \
  --database neo4j \
  --query "她最担心什么" \
  --character-id elaina
```

### 5.2 zep（7688）

```bash
uv run python memory_bench/scripts/probe_graphiti.py \
  --backend neo4j \
  --memory-system zep \
  --neo4j-uri bolt://127.0.0.1:7688 \
  --database neo4j \
  --query "她最担心什么" \
  --character-id elaina
```

### 5.3 cognee（7689）

```bash
uv run python memory_bench/scripts/probe_graphiti.py \
  --backend neo4j \
  --memory-system cognee \
  --neo4j-uri bolt://127.0.0.1:7689 \
  --database neo4j \
  --query "她最担心什么" \
  --character-id elaina
```

---

## 6. 说明

- 当前图谱后端仅支持 `neo4j`。
- probe 仅查询已有图谱，不会自动写入事件。
- `memory_system` 用于标记与过滤；多系统隔离由多实例端口与独立数据目录保障。

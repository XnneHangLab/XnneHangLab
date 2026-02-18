# Neo4j 一鍵導入（Graphify V0）

本文提供從 `graphify_pipeline.py` 產生 Cypher，到匯入 Neo4j（mem0/zep/cognee）並在 Neo4j Browser 驗證的最短流程。

## 0. 前置條件

- 已安裝 Docker 與 Docker Compose。
- 已有輸入 JSONL（例如：`memory_bench/tests/fixtures/export_sample.jsonl`）。
- 使用本 repo 新增腳本：`memory_bench/scripts/neo4j_apply_cypher.py`。

---

## 1) 啟動指定 Neo4j instance（示例：mem0）

```bash
docker compose -f memory_bench/docker-compose.neo4j.yml up -d neo4j_mem0
```

如需其他 instance：

```bash
docker compose -f memory_bench/docker-compose.neo4j.yml up -d neo4j_zep
docker compose -f memory_bench/docker-compose.neo4j.yml up -d neo4j_cognee
```

---

## 2) 跑 Graphify Pipeline（reset + run）產生 Neo4j Cypher

> 預設 `--cypher-out-dir` 為 `<out_dir>/neo4j`。

```bash
uv run python memory_bench/scripts/graphify_pipeline.py reset \
  --state-db memory_bench/state/graphify/state.sqlite \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --reset-output
```

```bash
uv run python memory_bench/scripts/graphify_pipeline.py run \
  --input memory_bench/tests/fixtures/export_sample.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --state-db memory_bench/state/graphify/state.sqlite \
  --prefix graph
```

產物（由 `neo4j_export_cypher.py` 生成）：

- `memory_bench/logs/replay_mem0/graphify/neo4j/graph_constraints.cypher`
- `memory_bench/logs/replay_mem0/graphify/neo4j/graph_import.cypher`

---

## 3) 一鍵導入 Cypher（constraints -> import）

腳本會自動依 target 對應：

- `mem0` -> `membench-neo4j-mem0`
- `zep` -> `membench-neo4j-zep`
- `cognee` -> `membench-neo4j-cognee`

並使用 Python 讀取 Cypher 檔內容後，透過 `docker exec -i <container> cypher-shell -u neo4j -p neo4jneo4j` 的 stdin 餵入（使用容器預設 database）。

### 指令示例（mem0 / zep / cognee 各一條）

```bash
uv run python memory_bench/scripts/neo4j_apply_cypher.py mem0 memory_bench/logs/replay_mem0/graphify/neo4j graph
uv run python memory_bench/scripts/neo4j_apply_cypher.py zep  memory_bench/logs/replay_zep/graphify/neo4j graph
uv run python memory_bench/scripts/neo4j_apply_cypher.py cognee memory_bench/logs/replay_cognee/graphify/neo4j graph
```

若你省略 `cypher_dir`，腳本會使用：`<GRAPHIFY_OUT_DIR>/neo4j`（預設 `GRAPHIFY_OUT_DIR=memory_bench/logs/replay_mem0/graphify`）。

bash：

```bash
GRAPHIFY_OUT_DIR=memory_bench/logs/replay_mem0/graphify \
  uv run python memory_bench/scripts/neo4j_apply_cypher.py mem0 graph
```

PowerShell：

```powershell
$env:GRAPHIFY_OUT_DIR="memory_bench/logs/replay_mem0/graphify"; uv run python memory_bench/scripts/neo4j_apply_cypher.py mem0 graph
```

---


## 4) Neo4j Browser 連線資訊

三個 instance 的 Browser URL：

- mem0: `http://localhost:7474`
- zep: `http://localhost:7475`
- cognee: `http://localhost:7476`

登入帳密（相同）：

- username: `neo4j`
- password: `neo4jneo4j`

Browser 預設 database 為 `neo4j`，一般不需要手動切換 database。

---

## 5) 可視化/驗證查詢（至少 5 條）

1. **Node / Relationship 總數**

```cypher
MATCH (n:Node) RETURN count(n) AS node_count;
MATCH ()-[r:REL]->() RETURN count(r) AS rel_count;
```

2. **Relationship type 分佈**

```cypher
MATCH ()-[r:REL]->()
RETURN r.type AS rel_type, count(*) AS cnt
ORDER BY cnt DESC;
```

3. **拉 user -> memoryitem 的圖**

```cypher
MATCH (u:Node)-[r:REL]->(m:Node)
WHERE 'user' IN u.labels AND 'memoryitem' IN m.labels
RETURN u, r, m
LIMIT 100;
```

4. **拉 memoryitem -> agent/scene/conv 子圖**

```cypher
MATCH (m:Node)-[r:REL]->(x:Node)
WHERE 'memoryitem' IN m.labels
  AND any(lbl IN x.labels WHERE lbl IN ['agent', 'scene', 'conv'])
RETURN m, r, x
LIMIT 200;
```

5. **查某個 memoryitem 的 data / created_at**

```cypher
MATCH (m:Node)
WHERE 'memoryitem' IN m.labels AND m.id = $memoryitem_id
RETURN m.id AS id, m.data AS data, m.created_at AS created_at;
```

執行範例（Browser 參數）：

```cypher
:param memoryitem_id => 'memoryitem:example-id';
```

---

## 6) 故障排除

- `Container ... is not running`：先 `docker compose ... up -d neo4j_<target>`。
- `Constraints/Import file not found`：檢查 `<prefix>_constraints.cypher`、`<prefix>_import.cypher` 檔名與路徑。
- 匯入失敗時，腳本會透過統一 logger 輸出錯誤並以非 0 退出碼結束，可直接用於 CI 或 shell pipeline。

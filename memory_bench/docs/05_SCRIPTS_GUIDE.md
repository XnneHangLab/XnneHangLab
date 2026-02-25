# Memory Bench 脚本使用手册（scripts/）

> 目标：解释 `memory_bench/scripts/` 下每个脚本的作用、调用示例、输入输出与返回码。
> 适合"第一次接触 bench"的同学：尽量不需要读源码也能跑通。

---

## 1. 脚本总览

当前脚本目录（与仓库当前状态对齐）：

- **数据构建 / 标注**
  - `build_index.py`
  - `annotate_all.py`
  - `compile_events.py`

- **回放（Mem0）**
  - `replay_mem0.py`

- **语义抽取（Claim/Entity）**
  - `claimify_all.py`
  - `compiled_claims.py`
  - `tag_registry.py`（工具模块）

- **图谱导出 → Neo4j**
  - `mem0_to_graph.py`（原 graphify_export.py）
  - `claims_to_graph.py`
  - `graph_to_cypher.py`（原 neo4j_export_cypher.py）
  - `neo4j_apply_cypher.py`
  - `latest_file.py`

- **工具模块**（非 CLI 主入口）
  - `bench_logger.py`（统一彩色日志）
  - `rate_limiter.py`（LLM API 令牌桶 + 并发控制）
  - `tag_registry.py`（tag 归一化与候选选择）

---

## 2. 通用运行方式

在仓库根目录执行：

```bash
uv run memory_bench/scripts/<script>.py -h
```

> **注意：** 不推荐使用 `uv run python -m memory_bench.scripts.<module>` 的方式，统一使用 `uv run` 直接调用脚本文件。

---

## 3. 推荐执行顺序（从原文到图谱）

### A) 原文 → events → Mem0

1. `build_index.py` — 生成章节索引
2. `annotate_all.py` — 章节标注为 events JSONL
3. `compile_events.py` — 拼接为 `compiled/all.jsonl`
4. `replay_mem0.py ingest` — 回放写入 Mem0
5. `replay_mem0.py probe`（可选）— 跑检索 probe 日志
6. `replay_mem0.py export` — 导出记忆快照

### B) export → claim/entity（语义图谱旁路）

7. `claimify_all.py` — 抽取 claim/entity
8. `compiled_claims.py` — 汇总去重为全局 compiled JSONL

### C) graph 导出 → Neo4j

9. `mem0_to_graph.py` — mem0 export → graph nodes/edges
10. `claims_to_graph.py` — compiled claims → graph nodes/edges
11. `graph_to_cypher.py` — nodes/edges → Neo4j cypher 脚本
12. `neo4j_apply_cypher.py` — 将 cypher 导入 Neo4j 容器

> 工作流编排由仓库根目录的 `justfile` 管理，详见 justfile 中的 recipe 定义。

---

## 4. `build_index.py`

### 作用

扫描 `memory_bench/data/source/raw/` 章节文件，关联 `norm/`，生成 `memory_bench/data/source/index.json`。

### 调用示例

```bash
uv run memory_bench/scripts/build_index.py
uv run memory_bench/scripts/build_index.py --force
uv run memory_bench/scripts/build_index.py --limit 5          # 仅前 5 章
uv run memory_bench/scripts/build_index.py --tail 3           # 仅最后 3 章
uv run memory_bench/scripts/build_index.py --offset 2 --limit 3  # 跳过前 2 章取 3 章
```

### 参数

| 参数 | 说明 |
|------|------|
| `--force` | 即使 index 已存在也强制重建 |
| `--limit N` | 仅索引前 N 章（按章节号排序） |
| `--tail N` | 仅索引后 N 章 |
| `--offset N` | 跳过前 N 章后再 limit/tail |

### 输入 / 输出

- 输入：`memory_bench/data/source/raw/*.md` + `norm/*.norm.md`（可选）
- 输出：`memory_bench/data/source/index.json`

---

## 5. `annotate_all.py`

### 作用

批量调用 LLM 将章节文本标注为严格 JSONL event 流。

### 调用示例

```bash
uv run memory_bench/scripts/annotate_all.py --workers 6
uv run memory_bench/scripts/annotate_all.py --only ch05,ch06
uv run memory_bench/scripts/annotate_all.py --only ch01 --workers 1 --force
```

### 参数

| 参数 | 说明 |
|------|------|
| `--workers` | 并发章节数 |
| `--force` | 覆盖重跑 |
| `--only` | 仅处理指定 conv_id（逗号分隔） |
| `--scene-id` | scene_id |
| `--character-id` | character_id |
| `--model` | LLM model |
| `--source` | 章节来源：`auto` / `raw` / `norm` |

### 环境变量（`memory_bench/.env.benchmark`）

- `BENCHMARK_LLM_API_KEY`（必须）
- `BENCHMARK_LLM_MODEL`（可选）
- `BENCHMARK_LLM_BASE_URL`（可选）
- `BENCHMARK_LLM_RATE_LIMIT`（可选，每分钟最大 LLM 调用次数，0 = 不限制）

优先级：CLI > `BENCHMARK_` 环境变量 > 脚本默认值。

### 输出

- 正式产物：`memory_bench/data/events/by_chapter/{conv_id}.jsonl`
- 调试日志：`logs/annotate_prompt/`、`logs/annotate_raw/`、`logs/annotate_meta/`

### 返回码

- `0`：全部 ok 或 skipped
- `1`：任意章节 failed

---

## 6. `compile_events.py`

### 作用

按 `index.json` 的章节顺序拼接 by_chapter JSONL，做严格校验后输出。

### 调用示例

```bash
uv run memory_bench/scripts/compile_events.py
uv run memory_bench/scripts/compile_events.py --chapters ch01,ch02
```

### 参数

| 参数 | 说明 |
|------|------|
| `--chapters` | 仅拼接指定章节（逗号分隔，按 index 顺序过滤） |
| `--out` | 输出 JSONL 路径 |
| `--mode` | 输出模式（默认 `preserve`） |

### 输入 / 输出

- 输入：`memory_bench/data/events/by_chapter/{conv_id}.jsonl`
- 输出：`memory_bench/data/events/compiled/all.jsonl`（默认）

---

## 7. `replay_mem0.py`

### 作用

将 benchmark 事件 JSONL 回放拆为 3 个子命令：

- `ingest` — 将事件流写入 Mem0（支持 checkpoint 断点续跑）
- `probe` — 对 probe 事件做 Mem0 检索并输出日志
- `export` — 导出当前 Mem0 全量快照

### 调用示例

```bash
uv run memory_bench/scripts/replay_mem0.py ingest
uv run memory_bench/scripts/replay_mem0.py ingest --isolation per_chapter
uv run memory_bench/scripts/replay_mem0.py probe --k 10
uv run memory_bench/scripts/replay_mem0.py export
uv run memory_bench/scripts/replay_mem0.py export --infer-owner --owner-fallback Agent
```

### 必需环境变量

需要同时配置 LLM 和 Embedding（共 6 项）：

- `BENCHMARK_LLM_API_KEY` / `BENCHMARK_LLM_BASE_URL` / `BENCHMARK_LLM_MODEL`
- `BENCHMARK_EMBEDDING_API_KEY` / `BENCHMARK_EMBEDDING_BASE_URL` / `BENCHMARK_EMBEDDING_MODEL`

---

## 8. `claimify_all.py`

### 作用

读取 mem0 export JSONL，按 conv_id 分组、按 chunk 调 LLM 抽取 claim/entity JSONL。

### 调用示例

```bash
uv run memory_bench/scripts/claimify_all.py \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl
uv run memory_bench/scripts/claimify_all.py \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl \
  --workers 2 --force
```

### 参数

| 参数 | 说明 |
|------|------|
| `--input`（必填） | mem0 export JSONL 路径 |
| `--workers` | 并发 conv 数 |
| `--force` | 覆盖重跑 |
| `--only` | 仅处理指定 conv_id |
| `--model` | LLM model |
| `--scene-id` / `--character-id` | 一致性校验 |
| `--max-items-per-chunk` / `--max-chars-per-chunk` | chunk 切分控制 |
| `--out-dir` | 输出根目录（默认 `memory_bench/data/claims`） |

### 输出

- 正式产物：`memory_bench/data/claims/by_conv/{conv_id}.jsonl`
- Tag registry：`memory_bench/resources/tag_registry.json`（增量更新）

---

## 9. `compiled_claims.py`

### 作用

将 `claimify_all.py` 产出的 by_conv JSONL 全量汇总去重。

### 调用示例

```bash
uv run memory_bench/scripts/compiled_claims.py --force
```

### 参数

| 参数 | 说明 |
|------|------|
| `--in-dir` | 输入目录（默认 by_conv） |
| `--out-dir` | 输出目录 |
| `--force` | 允许覆盖 |

### 输出

- `memory_bench/data/claims/compiled/entities.jsonl`
- `memory_bench/data/claims/compiled/claims.jsonl`
- `memory_bench/data/claims/compiled/compiled_meta.json`

---

## 10. `mem0_to_graph.py`

### 作用

消费 mem0 export JSONL，输出图谱 nodes/edges JSONL（增量幂等，通过 state.sqlite 管理）。

### 子命令

- `reset` — 重建 state.sqlite，可选清理输出
- `add` — 增量写 nodes/edges
- `dry-run` — 只解析统计，不写产物

### 调用示例

```bash
uv run memory_bench/scripts/mem0_to_graph.py add \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --state-db memory_bench/state/graphify/state.sqlite \
  --prefix graph

uv run memory_bench/scripts/mem0_to_graph.py reset \
  --state-db memory_bench/state/graphify/state.sqlite \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --reset-output
```

---

## 11. `claims_to_graph.py`

### 作用

将 compiled claims/entities JSONL 转换为图谱 nodes/edges JSONL。

### 子命令

- `add` — 导出
- `dry-run` — 只解析统计

### 调用示例

```bash
uv run memory_bench/scripts/claims_to_graph.py add
uv run memory_bench/scripts/claims_to_graph.py dry-run
```

---

## 12. `graph_to_cypher.py`

### 作用

将 mem0_to_graph / claims_to_graph 输出的 nodes/edges JSONL 转为 Neo4j 导入用的 cypher 脚本。

### 调用示例

```bash
uv run memory_bench/scripts/graph_to_cypher.py \
  --nodes memory_bench/logs/replay_mem0/graphify/graph_nodes_*.jsonl \
  --edges memory_bench/logs/replay_mem0/graphify/graph_edges_*.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify/neo4j \
  --prefix graph
```

### 参数

| 参数 | 说明 |
|------|------|
| `--nodes`（必填） | graph_nodes JSONL 路径 |
| `--edges`（必填） | graph_edges JSONL 路径 |
| `--out-dir`（必填） | 输出目录 |
| `--prefix` | 输出文件名前缀（默认 `graph`） |
| `--dry-run` | 只解析统计 |

### 输出

- `<prefix>_constraints.cypher`
- `<prefix>_import.cypher`
- `<prefix>_report.json`

---

## 13. `latest_file.py`

### 作用

按 glob 模式获取目标目录下最新文件路径（stdout 输出，适合在 justfile 中用变量捕获）。

### 调用示例

```bash
uv run memory_bench/scripts/latest_file.py \
  --export-dir memory_bench/logs/replay_mem0 \
  --glob "export_*.jsonl"

uv run memory_bench/scripts/latest_file.py \
  --export-dir memory_bench/logs/claims/graphify \
  --glob "claims_nodes_*.jsonl"
```

---

## 14. `neo4j_apply_cypher.py`

### 作用

将 cypher 文件一键导入指定 Neo4j docker 容器。

### 目标实例

- `mem0`
- `zep`
- `cognee`

### 调用示例

```bash
uv run memory_bench/scripts/neo4j_apply_cypher.py mem0 \
  --constraints path/to/graph_constraints_*.cypher \
  --import-file path/to/graph_import_*.cypher

uv run memory_bench/scripts/neo4j_apply_cypher.py mem0 \
  --constraints path/to/constraints.cypher \
  --import-file path/to/import.cypher \
  --dry-run
```

### 参数

| 参数 | 说明 |
|------|------|
| 位置参数 | 目标实例：`mem0` / `zep` / `cognee` |
| `--constraints`（必填） | constraints cypher 文件路径 |
| `--import-file`（必填） | import cypher 文件路径 |
| `--dry-run` | 只打印命令，不执行 |

---

## 15. 工具模块说明

| 模块 | 说明 |
|------|------|
| `bench_logger.py` | 统一彩色日志（被多数脚本复用） |
| `rate_limiter.py` | LLM API 令牌桶 + 并发控制 + 彩色日志 |
| `tag_registry.py` | tag 归一化与候选选择（由 claimify 使用） |

---

## 16. 一套可复制的完整流程

```bash
# 1) index
uv run memory_bench/scripts/build_index.py

# 2) annotate
uv run memory_bench/scripts/annotate_all.py --workers 6

# 3) compile
uv run memory_bench/scripts/compile_events.py

# 4) mem0 ingest + export
uv run memory_bench/scripts/replay_mem0.py ingest
uv run memory_bench/scripts/replay_mem0.py export

# 5) claimify + compile claims
latest_export=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/replay_mem0)
uv run memory_bench/scripts/claimify_all.py --input "$latest_export"
uv run memory_bench/scripts/compiled_claims.py --force

# 6) mem0 graph → cypher
just reset-mem0-graph
just mem0-to-graph
just mem0-graph-to-cypher

# 7) claims graph → cypher
just claim-items-to-cypher

# 8) 导入 Neo4j
just neo4j-apply-cypher
```

> 步骤 6-8 的编排由 justfile 管理，也可用 `just mem0-rerun` 一键跑完全流程。

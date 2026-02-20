# Memory Bench 脚本使用手册（scripts/）

> 目标：解释 `memory_bench/scripts/` 下每个脚本的作用、调用示例、输入输出、返回码与排错方式。
> 适合“第一次接触 bench”的同学：尽量不需要读源码也能跑通。

---

## 1. 脚本总览

当前脚本目录（与仓库当前状态对齐）：

- 数据构建 / 标注
  - `memory_bench/scripts/build_index.py`
  - `memory_bench/scripts/annotate_all.py`
  - `memory_bench/scripts/compile_events.py`

- 回放（Mem0）
  - `memory_bench/scripts/replay_mem0.py`

- 语义抽取（Claim/Entity）
  - `memory_bench/scripts/claimify_all.py`
  - `memory_bench/scripts/compiled_claims.py`
  - `memory_bench/scripts/tag_registry.py`（工具模块）

- 图谱导出（Graphify V0 + Neo4j）
  - `memory_bench/scripts/graphify_export.py`
  - `memory_bench/scripts/neo4j_export_cypher.py`
  - `memory_bench/scripts/graphify_pipeline.py`
  - `memory_bench/scripts/graphify_pipeline_latest.py`
  - `memory_bench/scripts/neo4j_apply_cypher.py`

- 统一日志
  - `memory_bench/scripts/bench_logger.py`（工具模块）

---

## 2. 推荐执行顺序（从原文到图谱）

### A) 原文 → events → Mem0

1) `build_index.py` 生成章节索引
2) `annotate_all.py` 章节标注为 events JSONL
3) `compile_events.py` 拼接为 `compiled/all.jsonl`
4) `replay_mem0.py ingest` 回放写入 Mem0
5) `replay_mem0.py probe`（可选）跑检索 probe 日志
6) `replay_mem0.py export` 导出记忆快照

### B) export → claim/entity（语义图谱旁路）

7) `claimify_all.py` 抽取 claim/entity（按 conv_id 分组、按 chunk 调 LLM）
8) `compiled_claims.py` 汇总去重为全局 compiled JSONL

### C) export → graphify（元数据归属图）→ Neo4j

9) `graphify_pipeline_latest.py`（推荐）自动选择最新 export 并一键运行：
   - graphify_export(add)：生成 nodes/edges + state.sqlite 增量
   - neo4j_export_cypher：生成约束与导入脚本

10) `neo4j_apply_cypher.py` 将 cypher 导入指定 Neo4j docker 容器实例

---

## 3. 通用运行方式（推荐）

在仓库根目录执行：

```bash
uv run python memory_bench/scripts/<script_name>.py -h
```

对以模块形式提供 CLI 的脚本：

```bash
uv run python -m memory_bench.scripts.<module_name> -h
```

---

## 4. `build_index.py`

### 4.1 作用

扫描 `memory_bench/data/source/raw/` 章节文件，并尝试关联 `memory_bench/data/source/norm/`，生成：

- `memory_bench/data/source/index.json`

这是 `annotate_all.py` 与 `compile_events.py` 的前置输入。

### 4.2 调用示例

```bash
uv run python memory_bench/scripts/build_index.py
```

### 4.3 输入 / 输出

- 输入：
  - `memory_bench/data/source/raw/*.md`
  - `memory_bench/data/source/norm/*.norm.md`（可缺省）
- 输出：
  - `memory_bench/data/source/index.json`

### 4.4 返回码

- 正常：0
- 未捕获异常：非 0（例如路径权限）

---

## 5. `annotate_all.py`

### 5.1 作用

批量读取章节文本，调用 LLM 标注为**严格 JSONL event 流**并强校验后写入：

- 正式事件文件：`memory_bench/data/events/by_chapter/{conv_id}.jsonl`
- 调试日志：
  - `memory_bench/logs/annotate_prompt/{conv_id}.txt`
  - `memory_bench/logs/annotate_raw/{conv_id}.txt`
  - `memory_bench/logs/annotate_meta/{conv_id}.json`

### 5.2 CLI 帮助

```bash
uv run python memory_bench/scripts/annotate_all.py -h
```

常用参数：

- `--workers`：并发章节数
- `--force`：覆盖重跑
- `--only ch01,ch02`：仅处理指定 conv_id
- `--scene-id` / `--character-id`
- `--model`
- `--source {auto,raw,norm}`

### 5.3 最常用调用

```bash
uv run python memory_bench/scripts/annotate_all.py --workers 6
```

仅跑两个章节：

```bash
uv run python memory_bench/scripts/annotate_all.py --only ch05,ch06
```

### 5.4 环境变量（`memory_bench/.env.benchmark`）

- `BENCHMARK_OPENAI_API_KEY`（必须）
- `BENCHMARK_OPENAI_MODEL`（可选）
- `BENCHMARK_OPENAI_BASE_URL`（可选，默认走 SDK 默认）
- `BENCHMARK_WORKERS` / `BENCHMARK_SOURCE` / `BENCHMARK_SCENE_ID` / `BENCHMARK_CHARACTER_ID`（可选）

优先级：CLI > `BENCHMARK_` 环境变量 > 脚本默认值。

### 5.5 返回码

- `0`：全部章节 `ok` 或 `skipped`
- `1`：任意章节 `failed`

### 5.6 失败定位

失败也会保留三类日志，便于回溯：

- prompt：`logs/annotate_prompt/{conv_id}.txt`
- raw：`logs/annotate_raw/{conv_id}.txt`
- meta：`logs/annotate_meta/{conv_id}.json`（含 `error_message`）

并且失败不会留下半截正式产物（先写 `.tmp`，校验通过后再替换）。

---

## 6. `compile_events.py`

### 6.1 作用

按 `memory_bench/data/source/index.json` 的章节顺序拼接：

- 输入：`memory_bench/data/events/by_chapter/{conv_id}.jsonl`
- 输出：`memory_bench/data/events/compiled/all.jsonl`（默认）

并做严格校验：

- 文件不存在/空文件 -> 失败
- 空行 -> 失败
- 非法 JSON -> 失败
- 缺少 required fields -> 失败
- `obj["conv_id"]` 不等于当前章节 -> 失败
- `turn_id` 必须从 1 开始严格 +1 -> 失败

输出为 `preserve` 模式：逐行校验，但写出时保留原始 JSON 文本行。

### 6.2 CLI 帮助与示例

```bash
uv run python memory_bench/scripts/compile_events.py -h
```

全量拼接：

```bash
uv run python memory_bench/scripts/compile_events.py
```

仅拼接指定章节（按 index 顺序过滤）：

```bash
uv run python memory_bench/scripts/compile_events.py --chapters ch01,ch02
```

### 6.3 返回码

- `0`：成功
- `1`：失败（任意校验失败）

---

## 7. `replay_mem0.py`（ingest / probe / export）

### 7.1 作用

将 benchmark 事件 JSONL 回放拆为 3 个子命令：

- `ingest`：将事件流按 conv 分组写入 Mem0，并保存 checkpoint（支持断点续跑）
- `probe`：只对 tags 含 `probe` 的事件做 Mem0 检索并输出日志
- `export`：导出当前 Mem0 collection 的全量快照（Qdrant scroll）

Mem0 使用本地持久化 Qdrant（默认 `memory_bench/state/qdrant_storage`），可跨进程共享状态。

### 7.2 CLI 帮助

```bash
uv run python memory_bench/scripts/replay_mem0.py -h
```

### 7.3 必需环境变量（强校验）

脚本会读取 `memory_bench/.env.benchmark`（override=True），并强制要求：

- `BENCHMARK_OPENAI_API_KEY`
- `BENCHMARK_OPENAI_BASE_URL`
- `BENCHMARK_OPENAI_MODEL`
- `BENCHMARK_OPENAI_EMBEDDING_MODEL`

### 7.4 常用示例

增量 ingest：

```bash
uv run python memory_bench/scripts/replay_mem0.py ingest
```

章节级隔离（ablation）：

```bash
uv run python memory_bench/scripts/replay_mem0.py ingest --isolation per_chapter
```

probe：

```bash
uv run python memory_bench/scripts/replay_mem0.py probe --k 10
```

export：

```bash
uv run python memory_bench/scripts/replay_mem0.py export

# 可选：显式指定 owner 推断输入与回退策略
uv run python memory_bench/scripts/replay_mem0.py export \
  --events memory_bench/data/events/compiled/all.jsonl \
  --infer-owner \
  --owner-fallback Agent
```

说明：

- `export` 默认会将 owner 推断结果写入 payload（如 `owner_type`/`owner_id` 等字段）；
- 基准用户 ID 默认 `xnne`（可由 `BENCHMARK_USER_ID` 覆盖）。

### 7.5 返回码

- `0`：成功
- `1`：失败（输入缺失、JSON 非法、env 缺失或 mem0 不可用等）

---

## 8. `claimify_all.py`

### 8.1 作用

读取 `replay_mem0.py export` 导出的 JSONL（每行一个 memory item），按 `conv_id` 分组、并按 chunk 调用 LLM 抽取并严格校验 claim/entity JSONL：

- 正式产物：`memory_bench/data/claims/by_conv/{conv_id}.jsonl`
- 调试日志（按 conv + chunk）：
  - `memory_bench/logs/claimify_prompt/{conv_id}__cXX.txt`
  - `memory_bench/logs/claimify_raw/{conv_id}__cXX.txt`
  - `memory_bench/logs/claimify_meta/{conv_id}.json`

默认提示词：`memory_bench/docs/23_CLAIM_EXTRACTOR_PROMPT.md`

此外会维护 tag registry（用于候选 tag 复用，减少近义重复）：

- registry 路径：`memory_bench/resources/tag_registry.json`
- 行为：
  - 文件不存在时：脚本会创建一个空 registry（version=1, tags=[]）再写入；
  - 抽取成功后：会从本次产出的 Tag 实体增量更新 `tags[]` 的 count/first_seen/last_seen；
  - 下次抽取时：会把 TopK 候选 tags 注入 prompt（见 prompt 中的 `[CANDIDATE_TAGS]`）。

### 8.2 CLI 帮助

```bash
uv run python memory_bench/scripts/claimify_all.py -h
```

关键参数：

- `--input`（必填）：mem0 export JSONL
- `--workers`：并发 conv 数
- `--force`：覆盖重跑
- `--only ch01,ch02`
- `--model`
- `--scene-id` / `--character-id`：输入强一致性校验（不一致直接失败）
- `--max-items-per-chunk` / `--max-chars-per-chunk`：chunk 切分控制
- `--out-dir`：输出根目录（默认 `memory_bench/data/claims`）

### 8.3 常用示例

```bash
uv run python memory_bench/scripts/claimify_all.py \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl
```

### 8.4 返回码

- `0`：全部 `ok` 或 `skipped`
- `1`：任意 conv `failed`

---

## 9. `compiled_claims.py`

### 9.1 作用

将 `claimify_all.py` 产出的 `memory_bench/data/claims/by_conv/*.jsonl` 全量汇总去重，输出：

- `memory_bench/data/claims/compiled/entities.jsonl`
- `memory_bench/data/claims/compiled/claims.jsonl`
- `memory_bench/data/claims/compiled/compiled_meta.json`

### 9.2 调用方式（模块运行）

```bash
uv run python -m memory_bench.scripts.compiled_claims -h
```

常用：

```bash
uv run python -m memory_bench.scripts.compiled_claims --force
```

### 9.3 返回码

- 正常：0
- 输入/校验失败：抛异常（uv 会显示 traceback）

---

## 10. `graphify_export.py`（V0 元数据归属图）

### 10.1 作用

消费 mem0 export JSONL，输出 V0 图谱结构（只做元数据归属图，不做语义抽取）：

- nodes JSONL
- edges JSONL
- report JSON
- 支持增量幂等：`state.sqlite` 记录 processed_key（payload.hash 优先，否则 point id）

当前边语义（收敛版）：

- `Character -[:OWNS_MEMORY]-> MemoryItem`（唯一 owner）；
- `Agent -[:ACTOR]-> Character`（Agent 身份映射）；
- `MemoryItem -[:HAS_CHARACTER]-> Character` 仍保留；
- 不再生成 `MemoryItem -[:TARGETS_AGENT]-> Agent`。

子命令：

- `reset`：重建 state.sqlite，可选清理输出
- `add`：增量写 nodes/edges + 更新 state
- `dry-run`：只解析/统计，不写产物、不写 state

### 10.2 CLI 帮助与示例

```bash
uv run python memory_bench/scripts/graphify_export.py -h
```

dry-run：

```bash
uv run python memory_bench/scripts/graphify_export.py dry-run \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl
```

add：

```bash
uv run python memory_bench/scripts/graphify_export.py add \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --state-db memory_bench/state/graphify/state.sqlite
```

### 10.3 返回码

- `0`：成功
- `1`：失败（输入不可读/解析异常/strict 模式报错等）

---

## 11. `neo4j_export_cypher.py`

### 11.1 作用

将 graphify 输出的 nodes/edges JSONL 转为 Neo4j 可导入的 cypher：

- `<prefix>_constraints.cypher`
- `<prefix>_import.cypher`
- `<prefix>_report.json`

### 11.2 CLI 示例

```bash
uv run python memory_bench/scripts/neo4j_export_cypher.py \
  --nodes memory_bench/logs/replay_mem0/graphify/graph_nodes_*.jsonl \
  --edges memory_bench/logs/replay_mem0/graphify/graph_edges_*.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify/neo4j \
  --prefix graph
```

---

## 12. `graphify_pipeline.py`（推荐入口）

### 12.1 作用

一体化串联：

- `graphify_export(add|dry-run)`
- `neo4j_export_cypher`（仅 run 时默认启用，dry-run 固定跳过）

### 12.2 调用方式（模块运行）

```bash
uv run python -m memory_bench.scripts.graphify_pipeline -h
```

run：

```bash
uv run python -m memory_bench.scripts.graphify_pipeline run \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --state-db memory_bench/state/graphify/state.sqlite
```

dry-run：

```bash
uv run python -m memory_bench.scripts.graphify_pipeline dry-run \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl
```

reset：

```bash
uv run python -m memory_bench.scripts.graphify_pipeline reset \
  --state-db memory_bench/state/graphify/state.sqlite \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --reset-output
```

---

## 13. `graphify_pipeline_latest.py`（自动选择最新 export）

### 13.1 作用

- 自动扫描 `memory_bench/logs/replay_mem0/` 下的 `export_*.jsonl`
- 选择时间线上最新的一个作为输入
- 调用 `graphify_pipeline.run` 执行 graphify + neo4j_export_cypher（默认开启）
- 若目录下没有任何 export 文件，直接报错退出

### 13.2 调用方式（模块运行）

```bash
uv run python -m memory_bench.scripts.graphify_pipeline_latest -h
```

常用：

```bash
uv run python -m memory_bench.scripts.graphify_pipeline_latest \
  --export-dir memory_bench/logs/replay_mem0 \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --state-db memory_bench/state/graphify/state.sqlite
```

---

## 14. `neo4j_apply_cypher.py`

### 14.1 作用

将 `neo4j_export_cypher.py` 生成的 cypher 文件，一键导入指定 Neo4j docker 容器。

目标实例枚举：

- `mem0`
- `zep`
- `cognee`

### 14.2 调用方式（模块运行）

```bash
uv run python -m memory_bench.scripts.neo4j_apply_cypher --dry-run mem0 graph
```

实际执行（示例）：

```bash
uv run python -m memory_bench.scripts.neo4j_apply_cypher mem0 \
  memory_bench/logs/replay_mem0/graphify/neo4j graph
```

---

## 15. 工具模块说明

- `bench_logger.py`：统一彩色日志（被多数脚本复用），非 CLI
- `tag_registry.py`：tag 归一化与候选选择工具（由 claimify 使用），非 CLI 主入口
  - 默认 registry 文件：`memory_bench/resources/tag_registry.json`

---

## 16. 一套可复制的完整流程（从原文到 Claim + Graphify）

```bash
# 1) index
uv run python memory_bench/scripts/build_index.py

# 2) annotate
uv run python memory_bench/scripts/annotate_all.py --only ch01 --workers 1
uv run python memory_bench/scripts/annotate_all.py --workers 6

# 3) compile
uv run python memory_bench/scripts/compile_events.py

# 4) mem0 ingest + export
uv run python memory_bench/scripts/replay_mem0.py ingest
uv run python memory_bench/scripts/replay_mem0.py export

# 5) claimify + compile claims
uv run python memory_bench/scripts/claimify_all.py \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl
uv run python -m memory_bench.scripts.compiled_claims --force

# 6) graphify + neo4j cypher（自动选择最新 export）
uv run python -m memory_bench.scripts.graphify_pipeline_latest \
  --export-dir memory_bench/logs/replay_mem0 \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --state-db memory_bench/state/graphify/state.sqlite
```

```

# memory_bench

`memory_bench` 是仓库内的独立模块，用于承载“记忆基准（Memory Bench）”相关的：

- 原始章节语料（`memory_bench/data/source/raw/`）
- 规范化章节语料（`memory_bench/data/source/norm/`，可选）
- 机器可读索引（`memory_bench/data/source/index.json`）
- 工作流文档与提示词（`memory_bench/docs/`）
- 工作流脚本（`memory_bench/scripts/`）
- 标注产物、回放状态与调试日志（运行后生成在 `memory_bench/data/*`、`memory_bench/logs/*`、`memory_bench/state/*`）

本模块目标是：让从“章节原文”到“可重放事件流”、再到“Mem0 检索日志/记忆快照”、再到“Claim/Entity 图谱旁路产物”，整个链路 **可复现、可审查、可对照**。

---

## 目录结构（核心）

```text
memory_bench/
├─ README.md
├─ docs/
│  ├─ 00_DOC_MAP.md
│  ├─ 05_SCRIPTS_GUIDE.md
│  ├─ 10_SYSTEM_PROMPTS.md
│  ├─ 20_ANNOTATOR_PROMPT.md
│  ├─ 21_SCENE_CANON.md
│  ├─ 22_PERSONA_CANON.md
│  ├─ 23_CLAIM_EXTRACTOR_PROMPT.md
│  ├─ 30_GENERATOR_PROMPT.md
│  ├─ 40_ANCHORS_AND_TEMPLATES.md
│  └─ graphify_spec.md
├─ scripts/
│  ├─ annotate_all.py
│  ├─ bench_logger.py
│  ├─ build_index.py
│  ├─ claimify_all.py
│  ├─ compile_events.py
│  ├─ compiled_claims.py
│  ├─ replay_mem0.py
│  ├─ tag_registry.py
│  ├─ graphify_export.py
│  ├─ graphify_pipeline.py
│  ├─ latest_file.py
│  ├─ latest_export_file.py  (兼容别名入口)
│  ├─ neo4j_export_cypher.py
│  └─ neo4j_apply_cypher.py
├─ resources/
│  └─ tag_registry.json
├─ data/
│  ├─ source/
│  │  ├─ index.json
│  │  ├─ raw/   (chXX_*.md)
│  │  └─ norm/  (chXX_*.norm.md, optional)
│  ├─ events/
│  │  ├─ by_chapter/ (chXX.jsonl)
│  │  └─ compiled/   (all.jsonl)
│  └─ claims/
│     ├─ by_conv/    (chXX.jsonl)
│     └─ compiled/   (entities.jsonl / claims.jsonl / compiled_meta.json)
├─ logs/
│  ├─ annotate_prompt/   (per chapter)
│  ├─ annotate_raw/      (per chapter)
│  ├─ annotate_meta/     (per chapter)
│  ├─ replay_mem0/       (probe/export logs)
│  ├─ claimify_prompt/   (per conv + chunk)
│  ├─ claimify_raw/      (per conv + chunk)
│  └─ claimify_meta/     (per conv)
└─ state/
   ├─ mem0_*.checkpoint.json
   ├─ qdrant_storage/...
   └─ graphify/ state.sqlite
```

---

## 通用运行方式（推荐）

在仓库根目录执行：

```bash
uv run python memory_bench/scripts/<script>.py -h
```

有些脚本以模块方式运行（例如 `compiled_claims.py`、`graphify_pipeline.py`、`neo4j_apply_cypher.py`），可用：

```bash
uv run python -m memory_bench.scripts.<module> -h
```

---

## 环境变量与配置（bench 专用）

多数脚本会尝试读取：

- `memory_bench/.env.benchmark`

### 必要变量（标注/抽取/回放会用到）

- `BENCHMARK_OPENAI_API_KEY`
- `BENCHMARK_OPENAI_BASE_URL`（OpenAI 兼容接口）
- `BENCHMARK_OPENAI_MODEL`（LLM）
- `BENCHMARK_OPENAI_EMBEDDING_MODEL`（仅 `replay_mem0.py` 必需）

> `annotate_all.py` / `claimify_all.py` 只强制需要 API KEY；
> `replay_mem0.py` 会强制检查四项都存在（LLM+Embedder 都要）。

---

## 一套可复制的完整流程

### A. 从章节原文 → 事件 JSONL → Mem0 回放/导出

```bash
# 1) 构建章节索引
uv run python memory_bench/scripts/build_index.py

# 2) 批量标注为 events（建议先小范围试跑）
uv run python memory_bench/scripts/annotate_all.py --only ch01 --workers 1
uv run python memory_bench/scripts/annotate_all.py --workers 6

# 3) 按 index 顺序拼接成单一 all.jsonl
uv run python memory_bench/scripts/compile_events.py

# 4) 回放写入 Mem0（默认跳过 filler，且不会把 probe 写入记忆）
uv run python memory_bench/scripts/replay_mem0.py ingest

# 5) 导出 Mem0 当前快照（供 claimify/graphify 使用）
uv run python memory_bench/scripts/replay_mem0.py export

# 可选：基于事件文本推断 owner（默认开启）
uv run python memory_bench/scripts/replay_mem0.py export \
  --events memory_bench/data/events/compiled/all.jsonl \
  --infer-owner \
  --owner-fallback Agent
```

产物重点看：

- `memory_bench/data/events/by_chapter/*.jsonl`
- `memory_bench/data/events/compiled/all.jsonl`
- `memory_bench/logs/replay_mem0/export_*.jsonl`
- `memory_bench/logs/replay_mem0/probe_*.jsonl`

---

### B. 从 Mem0 export → Claim/Entity JSONL → 全局编译（去重汇总）

```bash
# 6) 从 export 快照抽取 claim/entity（按 conv_id 分组；内部会按 chunk 调 LLM）
uv run python memory_bench/scripts/claimify_all.py \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl

说明：
- `claimify_all.py` 会维护一个 Tag 归一化/复用用的注册表：
  `memory_bench/resources/tag_registry.json`
- 该文件用于向 LLM 提供 TopK 候选 canonical tags，减少近义重复 Tag。
- 初始可为空；首次运行后会自动写入/更新。

# 7) 汇总 by_conv 到全局 compiled（Neo4j 友好）
uv run python -m memory_bench.scripts.compiled_claims --force
```

产物重点看：

- `memory_bench/data/claims/by_conv/*.jsonl`
- `memory_bench/data/claims/compiled/entities.jsonl`
- `memory_bench/data/claims/compiled/claims.jsonl`
- `memory_bench/data/claims/compiled/compiled_meta.json`

---

### C. Graphify（V0 元数据归属图）→ Neo4j Cypher → 一键导入 Neo4j

> Graphify V0 只做“归属/元数据”节点与关系：MemoryItem/User/Agent/Conversation/Scene/Character。
> 语义 Claim/Entity 图谱（reading/writing/daily）走 `claimify_all.py` + `compiled_claims.py`。

当前关系约束（收敛后）：

- `OWNS_MEMORY`：由 `Character -> MemoryItem` 表达唯一 owner；
- `ACTOR`：`Agent -> Character`（Agent 身份映射，仅此一条身份线）；
- 不再生成 `MemoryItem -> Agent` 的 `TARGETS_AGENT`。

```bash
# 8) Graphify pipeline：增量 graphify_export(add) + neo4j_export_cypher
latest_export=$(uv run python -m memory_bench.scripts.latest_file --export-dir memory_bench/logs/replay_mem0 --glob "export_*.jsonl")
uv run python -m memory_bench.scripts.graphify_pipeline run \
  --input "$latest_export" \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --state-db memory_bench/state/graphify/state.sqlite \
  --cypher-out-dir memory_bench/logs/replay_mem0/graphify/neo4j
```

然后导入 Neo4j（目标实例由 docker compose 管理）：

```bash
# 9) 将 cypher 导入指定目标 Neo4j（mem0 / zep / cognee）
uv run python -m memory_bench.scripts.neo4j_apply_cypher mem0 \
  memory_bench/logs/replay_mem0/graphify/neo4j graph
```

---

## 脚本简表

- `build_index.py`：raw/norm 扫描 → `data/source/index.json`
- `annotate_all.py`：章节文本 → 严格 JSONL events（by_chapter + 调试日志）
- `compile_events.py`：按 index 顺序拼接 → `events/compiled/all.jsonl`
- `replay_mem0.py`：ingest/probe/export（本地 qdrant 持久化 + checkpoint）
- `claimify_all.py`：mem0 export → claim/entity JSONL（by_conv + chunk 日志）+ tag registry 复用
  - registry：`memory_bench/resources/tag_registry.json`
- `compiled_claims.py`：by_conv 汇总去重 → compiled entities/claims
- `graphify_export.py`：mem0 export → V0 graph nodes/edges（增量/幂等）
- `neo4j_export_cypher.py`：nodes/edges JSONL → Neo4j cypher 脚本
- `latest_file.py`：获取目录下按 glob 匹配的最新文件路径（默认 `export_*.jsonl`，也可用于 `claims_nodes_*.jsonl` / `claims_edges_*.jsonl`）
- `latest_export_file.py`：兼容旧命令入口，内部转发到 `latest_file.py`
- `graphify_pipeline.py`：graphify_export + neo4j_export_cypher 一体化入口（由 justfile 组合 `--input`）
- `neo4j_apply_cypher.py`：将 cypher 导入指定 Neo4j docker 容器
- `bench_logger.py` / `tag_registry.py`：内部复用工具模块（非主 CLI）

---

## `index.json` 格式（供 annotate/compile 消费）

```json
[
  {
    "id": "ch01",
    "raw_path": "memory_bench/data/source/raw/ch01_xxx.md",
    "norm_path": "memory_bench/data/source/norm/ch01_xxx.norm.md"
  }
]
```

- `id`：章节 ID（`chXX`）
- `raw_path`：相对仓库根目录路径（必有）
- `norm_path`：相对仓库根目录路径（可为空字符串）

---

## 依赖安装（memory_bench 组）

如需安装 bench 相关依赖（含 mem0ai 等）：

```bash
uv sync --group memory_bench
```

---

## Done 校验建议（最少检查）

- `build_index.py` 后：`memory_bench/data/source/index.json` 存在且可解析
- `annotate_all.py` 后：`data/events/by_chapter/chXX.jsonl` 存在，且 `logs/annotate_meta/chXX.json` 无失败
- `compile_events.py` 后：`data/events/compiled/all.jsonl` 存在且拼接成功
- `replay_mem0.py export` 后：`logs/replay_mem0/export_*.jsonl` 有内容
- `claimify_all.py` 后：`data/claims/by_conv/chXX.jsonl` 存在
- `compiled_claims.py` 后：`data/claims/compiled/*.jsonl` + `compiled_meta.json` 存在
- `graphify_pipeline run` 后：`logs/replay_mem0/graphify/*nodes*.jsonl`、`*edges*.jsonl`、`neo4j/*.cypher` 存在
```


### Claims 图谱 nodes/edges 转 Cypher（示例）

```bash
claim_nodes=$(uv run python -m memory_bench.scripts.latest_file --export-dir memory_bench/logs/claims/graphify --glob "claims_nodes_*.jsonl")
claim_edges=$(uv run python -m memory_bench.scripts.latest_file --export-dir memory_bench/logs/claims/graphify --glob "claims_edges_*.jsonl")
uv run python memory_bench/scripts/neo4j_export_cypher.py \
  --nodes "$claim_nodes" \
  --edges "$claim_edges" \
  --out-dir memory_bench/logs/claims/graphify/neo4j \
  --prefix claims
```

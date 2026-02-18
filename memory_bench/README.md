# memory_bench

`memory_bench` 是仓库内的独立模块，用于承载记忆基准（Memory Bench）相关的：

- 原始章节语料（`memory_bench/data/source/raw/`）
- 规范化章节语料（`memory_bench/data/source/norm/`）
- 机器可读索引（`memory_bench/data/source/index.json`）
- 工作流文档与提示词（`memory_bench/docs/`）
- 章节索引与 LLM 标注脚本（`memory_bench/scripts/`）
- 标注产物与调试日志（运行后生成到 `memory_bench/data/events/` 与 `memory_bench/logs/`）

## 目录结构

```text
memory_bench/
├─ README.md
├─ pyproject.toml
├─ uv.lock
├─ scripts/
│  ├─ annotate_all.py
│  ├─ bench_logger.py
│  ├─ build_index.py
│  ├─ compile_events.py
│  └─ replay_mem0.py
├─ docs/
│  ├─ 00_DOC_MAP.md
│  ├─ 05_SCRIPTS_GUIDE.md
│  ├─ 10_SYSTEM_PROMPTS.md
│  ├─ 20_ANNOTATOR_PROMPT.md
│  ├─ 21_SCENE_CANON.md
│  ├─ 22_PERSONA_CANON.md
│  ├─ 30_GENERATOR_PROMPT.md
│  └─ 40_ANCHORS_AND_TEMPLATES.md
└─ data/
   ├─ events/                 # 运行 annotate_all.py 后生成
   │  ├─ by_chapter/
   │  │  └─ chXX.jsonl
   │  └─ compiled/
   │     └─ all.jsonl
   └─ source/
      ├─ index.json
      ├─ raw/
      │  └─ chXX_*.md
      └─ norm/
         └─ chXX_*.norm.md

# 运行 annotate_all.py 后还会新增：
# memory_bench/logs/
# ├─ annotate_meta/{conv_id}.json
# ├─ annotate_prompt/{conv_id}.txt
# └─ annotate_raw/{conv_id}.txt
```

## 脚本说明

### 1) 索引构建：`build_index.py`

脚本：`memory_bench/scripts/build_index.py`

功能：

1. 扫描 `memory_bench/data/source/raw/`；
2. 只收集匹配 `ch\d\d_*.md` 的文件；
3. 提取章节 ID（如 `ch01`）；
4. 按章节号升序排序（同章节号按文件名稳定排序）；
5. 关联可选的 `memory_bench/data/source/norm/` 规范化文件路径；
6. 生成 `memory_bench/data/source/index.json`。

#### 运行方式

> 在项目根目录执行：

```bash
uv run --project memory_bench ./memory_bench/scripts/build_index.py
```

> 或在 `memory_bench/` 目录执行：

```bash
uv run ./scripts/build_index.py
```

### 2) LLM 标注：`annotate_all.py`

脚本：`memory_bench/scripts/annotate_all.py`

功能：

1. 读取 `memory_bench/data/source/index.json`；
2. 按章节读取 `norm`（或按配置回退 `raw`）文本；
3. 调用 LLM 产出严格 JSONL event 流；
4. 通过 schema 与顺序校验后，原子写入章节事件文件；
5. 同步落盘 prompt/raw/meta 三类调试日志。

常用运行方式：

```bash
uv run python memory_bench/scripts/annotate_all.py --workers 6
```

只跑指定章节：

```bash
uv run python memory_bench/scripts/annotate_all.py --only ch01,ch02
```

输出路径：

- 事件（正式产物）：`memory_bench/data/events/by_chapter/{conv_id}.jsonl`
- 日志（调试定位）：
  - `memory_bench/logs/annotate_prompt/{conv_id}.txt`
  - `memory_bench/logs/annotate_raw/{conv_id}.txt`
  - `memory_bench/logs/annotate_meta/{conv_id}.json`

状态语义：

- `ok`：校验通过并写入正式 jsonl
- `skipped`：目标文件已存在且未加 `--force`
- `failed`：LLM 调用/格式校验/字段校验等任一步骤失败


### 3) 事件拼接：`compile_events.py`

脚本：`memory_bench/scripts/compile_events.py`

功能：

1. 读取 `memory_bench/data/source/index.json` 获取章节顺序；
2. 从 `memory_bench/data/events/by_chapter/{conv_id}.jsonl` 逐章拼接；
3. 逐行严格校验 JSONL（空行、非法 JSON、字段缺失、`conv_id` 不一致、`turn_id` 连续性）；
4. 在 `preserve` 模式下按原始文本写出（不重排 JSON，不 `json.dumps`）；
5. 原子写入 `memory_bench/data/events/compiled/all.jsonl`（先 `.tmp` 后 `os.replace`）。

常用运行方式：

```bash
uv run python memory_bench/scripts/compile_events.py
```

只拼接指定章节（按 index 顺序过滤）：

```bash
uv run python memory_bench/scripts/compile_events.py --chapters ch01,ch02
```

输出路径：

- 默认产物：`memory_bench/data/events/compiled/all.jsonl`
- 可通过 `--out` 覆盖输出路径


### 4) Mem0 重放：`replay_mem0.py`（ingest / probe / export）

脚本：`memory_bench/scripts/replay_mem0.py`

功能：

1. 将流程拆分为三个子命令：
   - `ingest`：增量写入事件到 Mem0，并维护 checkpoint
   - `probe`：只读取 `tags` 含 `probe` 的事件做检索，不写入 memory
   - `export`：导出当前 memory 状态快照（按 user_id）
2. 依据隔离模式生成 `user_id`：
   - `--isolation global` -> `scene_id:character_id`
   - `--isolation per_chapter` -> `scene_id:character_id:conv_id`
3. Mem0 使用本地持久化 Qdrant 向量存储（默认 `memory_bench/state/qdrant_storage`，collection 为 `memory_bench_{isolation}`），可跨进程复用；
4. ingest 支持 checkpoint 断点续跑（默认保存到 `memory_bench/state/`，记录 input hash 与 last_ingested_line）；
5. probe 输出标准化检索日志到 `memory_bench/logs/replay_mem0/probe_YYYYMMDD_HHMMSS.jsonl`；
6. export 输出快照到 `memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl`。

常用运行方式：

```bash
uv run python memory_bench/scripts/replay_mem0.py ingest --input memory_bench/data/events/compiled/all.jsonl
```

独立运行 probe（可反复执行不同参数）：

```bash
uv run python memory_bench/scripts/replay_mem0.py probe --k 10 --output memory_bench/logs/replay_mem0/probe_k10.jsonl
```

导出当前记忆快照：

```bash
uv run python memory_bench/scripts/replay_mem0.py export
```

常用过滤参数：

- `--skip-role ui,tool`
- `--skip-tags filler`
- `--only-tags canon_only,episodic,synthetic`
- `--write-probes`（默认关闭，避免 probe 污染记忆）
- `--batch-size 16`（批量写入 Memory.add）
- `--store-raw`（写入时优先 `infer=False`，让命中更接近原文）
- `--state-dir memory_bench/state`（checkpoint 与 Qdrant 本地存储根目录）
- `--checkpoint-interval 50`（每 N 条 ingest 成功后更新 checkpoint）
- `--force`（忽略旧 checkpoint，从头 ingest）

环境变量（优先读取 bench 前缀）：

- `BENCHMARK_OPENAI_API_KEY`（必需）
- `BENCHMARK_OPENAI_BASE_URL`（必需）
- `BENCHMARK_OPENAI_MODEL`（必需）
- `BENCHMARK_OPENAI_EMBEDDING_MODEL`（必需）

脚本会先尝试加载 `memory_bench/.env.benchmark`（`override=True`），并显式写入 Mem0 的 `llm/embedder/vector_store` 配置；不会回退读取 `OPENAI_*`。

### 5) 统一日志模块：`bench_logger.py`

`memory_bench/scripts/bench_logger.py` 为内部复用模块，提供统一日志格式（含 group 与 level），被 `build_index.py`、`annotate_all.py` 调用，不作为独立 CLI 使用。

### 6) Graphify + Neo4j V0 Pipeline：`graphify_pipeline.py`

脚本：`memory_bench/scripts/graphify_pipeline.py`

功能：

1. `run`：串联 `graphify_export.py add` 与 `neo4j_export_cypher.py export`；
2. `dry-run`：执行 `graphify_export.py dry-run`（固定不导出 cypher）；
3. `reset`：执行 `graphify_export.py reset`（可加 `--reset-output` 清理产物）。

#### 启动 Neo4j（docker compose）

```bash
docker compose -f memory_bench/docker-compose.neo4j.yml up -d neo4j_mem0
```

一键导入 Cypher（含 mem0/zep/cognee 示例）请参考：`docs/neo4j_import_v0.md`（主推跨平台 Python CLI：`uv run python memory_bench/scripts/neo4j_apply_cypher.py ...`）。

#### Pipeline 示例（基于 export sample fixture）

```bash
uv run python memory_bench/scripts/graphify_pipeline.py run \
  --input memory_bench/tests/fixtures/export_sample.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --state-db memory_bench/state/graphify/state.sqlite \
  --cypher-out-dir memory_bench/logs/replay_mem0/graphify/neo4j
```

```bash
uv run python memory_bench/scripts/graphify_pipeline.py dry-run \
  --input memory_bench/tests/fixtures/export_sample.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --state-db memory_bench/state/graphify/state.sqlite
```


```bash
uv run python memory_bench/scripts/graphify_pipeline.py reset \
  --state-db memory_bench/state/graphify/state.sqlite \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --reset-output
```

## `index.json` 格式（供 annotate_all.py 消费）

```json
[
  {
    "id": "ch01",
    "raw_path": "memory_bench/data/source/raw/ch01_xxx.md",
    "norm_path": "memory_bench/data/source/norm/ch01_xxx.norm.md"
  }
]
```

字段说明：

- `id`：章节前缀（`chXX`）
- `raw_path`：相对仓库根目录路径，不能为空
- `norm_path`：相对仓库根目录路径，可为空字符串（缺失时构建会产生 warning）


## 依赖安装（memory_bench 组）

仓库根 `pyproject.toml` 已增加 `memory_bench` dependency group（包含 `mem0ai`），并纳入默认组。

如需单独安装该组，可执行：

```bash
uv sync --group memory_bench
```

## Done 校验建议

运行索引脚本后，至少确认：

- `memory_bench/data/source/index.json` 存在；
- 可被 `json.loads` 正常解析；
- 列表长度与 `raw/` 下匹配 `ch\d{2,}_*.md` 文件数量一致；
- `raw_path` 全部非空。

如果跑了 `annotate_all.py`，还建议补充确认：

- `memory_bench/data/events/by_chapter/` 下存在对应章节 `*.jsonl`；
- `memory_bench/logs/annotate_meta/*.json` 中失败章节有明确 `error_message`；
- 重跑时未加 `--force` 的章节会被 `skipped`（而不是被覆盖）。

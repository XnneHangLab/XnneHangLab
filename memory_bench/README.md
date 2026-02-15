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
│  ├─ replay_mem0.py
│  ├─ replay_graphiti.py
│  └─ probe_graphiti.py
├─ docs/
│  ├─ 00_DOC_MAP.md
│  ├─ 05_SCRIPTS_GUIDE.md
│  ├─ 10_SYSTEM_PROMPTS.md
│  ├─ 20_ANNOTATOR_PROMPT.md
│  ├─ 21_SCENE_CANON.md
│  ├─ 22_PERSONA_CANON.md
│  ├─ 30_GENERATOR_PROMPT.md
│  ├─ 40_ANCHORS_AND_TEMPLATES.md
│  ├─ 50_GRAPHITI_NEO4J_DESIGN.md
│  └─ 51_NEO4J_LOCAL_SETUP.md
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


### 4) Mem0 重放：`replay_mem0.py`

脚本：`memory_bench/scripts/replay_mem0.py`

功能：

1. 流式读取事件 JSONL（支持 compiled 与 by_chapter 输入）；
2. 依据隔离模式生成 `user_id`：
   - `--isolation global` -> `scene_id:character_id`
   - `--isolation per_chapter` -> `scene_id:character_id:conv_id`
3. 按规则写入 Mem0（默认仅 `human/assistant` 且过滤 `ui/tool/filler`）；
4. 对 `tags` 包含 `probe` 的事件执行 `memory.search(...)`；
5. 运行时显示 replay 全量实时进度条（event 级，含 total 与百分比）；
6. 将每条 probe 结果写入 `memory_bench/logs/replay_mem0/run_YYYYMMDD_HHMMSS.jsonl`，包含 `probe_role_type/probe_role_name/user_id` 与 `hits_count/hits_preview/latency_ms`。

常用运行方式：

```bash
uv run python memory_bench/scripts/replay_mem0.py --input memory_bench/data/events/compiled/all.jsonl
```

切换章节级隔离：

```bash
uv run python memory_bench/scripts/replay_mem0.py --isolation per_chapter
```

常用过滤参数：

- `--skip-role ui,tool`
- `--skip-tags filler`
- `--only-tags canon_only,episodic,synthetic`
- `--write-probes`（默认关闭，避免 probe 污染记忆）
- `--batch-size 16`（批量写入 Memory.add，probe 前自动 flush）
- `--store-raw`（写入时优先 `infer=False`，让命中更接近原文）

环境变量（优先读取 bench 前缀）：

- `BENCHMARK_OPENAI_API_KEY`（或 `OPENAI_API_KEY`）
- `BENCHMARK_OPENAI_BASE_URL`（或 `OPENAI_BASE_URL` / `OPENAI_API_BASE`）
- `BENCHMARK_OPENAI_MODEL`（可选，回退 `OPENAI_MODEL`）

脚本会先尝试加载 `memory_bench/.env.benchmark`，并将上述值传递给 Mem0 初始化。

### 5) 统一日志模块：`bench_logger.py`

`memory_bench/scripts/bench_logger.py` 为内部复用模块，提供统一日志格式（含 group 与 level），被 `build_index.py`、`annotate_all.py` 调用，不作为独立 CLI 使用。

### 6) 图谱回放：`replay_graphiti.py`

运行前请先完成 Neo4j 本地部署（见 `memory_bench/docs/51_NEO4J_LOCAL_SETUP.md`）。

脚本：`memory_bench/scripts/replay_graphiti.py`

功能：

1. 支持两类输入：`--mode events`（事件图）与 `--mode memory_items`（记忆产物图）；
2. `events` 模式会创建 `Scene / Character / Conversation / Role / Utterance` 核心节点；
3. 将 `canon_only` 写为 `CanonFact` 节点；
4. 将 `episodic` 写为 `EpisodicEvent` 节点（含 `decay_score`）；
5. `memory_items` 模式写入 `MemoryItem`，并通过 `DERIVED_FROM` 关联回 `Utterance`；
6. 默认建议采用增量回放（不加 `--clear`），保留历史图并幂等 MERGE 更新。

后端通过 `--backend neo4j` 固定使用 Neo4j。

常用运行方式：

```bash
# 事件图（增量）
uv run python memory_bench/scripts/replay_graphiti.py --backend neo4j --mode events --memory-system mem0 --input memory_bench/data/events/compiled/all.jsonl

# 记忆层（增量，推荐默认）
uv run python memory_bench/scripts/replay_graphiti.py --backend neo4j --mode memory_items --memory-system mem0 --input memory_bench/logs/replay_mem0/mem0_written.jsonl
```

> 仅在需要全量重建时再使用 `--clear`。

### 7) 图谱 probe：`probe_graphiti.py`

脚本：`memory_bench/scripts/probe_graphiti.py`

功能：

1. 按 probe 文本检索 `Utterance` 内容；
2. 返回命中的 `CanonFact` / `EpisodicEvent` 关联；
3. 汇总 `Role -> Role` 的互动统计；
4. 支持单条查询和 probe JSONL 批量查询。

常用运行方式：

```bash
uv run python memory_bench/scripts/probe_graphiti.py --backend neo4j --memory-system mem0 --query "她最近担心什么" --character-id elaina
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

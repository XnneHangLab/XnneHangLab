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

- **Memory Chat Server**（`memory_bench/server/`）
  - `chat_server.py`（独立启动器 + CLI）
  - `router.py`（FastAPI router，可独立挂载到其他 app）
  - `claim_extractor.py`（实时 claim/entity 提取，`claimify_all.py` 的实时对应物）
  - `graph_writer.py`（实时图谱写入 Neo4j，离线管线的实时对应物）

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

> 步骤 6-8 的编排由 justfile 管理，也可用 `just mem0-rerun-add` 一键跑增量流程，`just mem0-rerun-force` 跑完全重建。

---

## 17. Memory Chat Server（`memory_bench/server/`）

### 作用

OpenAI 兼容的 `/v1/chat/completions` 代理服务，在 LLM 调用前后插入 mem0 记忆检索与写入。

架构：

```
AIChat Mod (C#)
    ↓  POST /v1/chat/completions
Memory Chat Server (FastAPI)
    ├─ mem0.search() → 检索相关记忆
    ├─ 注入 system prompt
    ├─ 转发真正的 LLM provider
    ├─ 异步 mem0.add() → 写入本轮对话
    │   └─ [--enable-graph] Graph Pipeline (后台)
    │       ├─ claim_extractor → LLM 提取 claim/entity
    │       └─ graph_writer → Cypher MERGE 写入 Neo4j
    └─ 返回标准 ChatCompletion response
```

### 文件结构

- `router.py` — FastAPI APIRouter，包含端点、记忆逻辑和 graph pipeline 后台任务。可独立挂载到任意 FastAPI app。
- `chat_server.py` — 独立启动器：CLI 参数解析、env 加载、mem0 初始化、graph pipeline 配置、uvicorn 启动。
- `claim_extractor.py` — 从 mem0.add() 结果中提取 claim/entity 记录（LLM-based）。
- `graph_writer.py` — 将 claim 记录通过 Cypher MERGE 写入 Neo4j。

### 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | 记忆增强的 chat 接口（非 streaming） |
| `/v1/models` | GET | 兼容性端点 |
| `/health` | GET | 健康检查 |

### 调用示例

```bash
# 通过 justfile
just memory-chat-server          # 默认端口 8080
just memory-chat-server 9090     # 自定义端口

# 直接调用
uv run memory_bench/server/chat_server.py --port 8080

# 指定所有参数
uv run memory_bench/server/chat_server.py \
  --chat-api-key sk-xxx \
  --chat-base-url https://openrouter.ai/api/v1 \
  --chat-model google/gemini-2.0-flash \
  --embedding-api-key sk-xxx \
  --embedding-base-url https://api.openai.com/v1 \
  --embedding-model text-embedding-3-small \
  --port 8080
```

### 环境变量

配置通过 `memory_bench/.env.benchmark` 加载，CLI 参数优先。

| 环境变量 | 说明 | 回退 |
|----------|------|------|
| `CHAT_API_KEY` | Chat LLM 的 API key | `BENCHMARK_LLM_API_KEY` |
| `CHAT_BASE_URL` | Chat LLM 的 base URL | `BENCHMARK_LLM_BASE_URL` |
| `CHAT_MODEL` | Chat 模型名 | `BENCHMARK_LLM_MODEL` |
| `MEM0_LLM_API_KEY` | Mem0 提取用 LLM 的 API key | `CHAT_API_KEY` |
| `MEM0_LLM_BASE_URL` | Mem0 提取用 LLM 的 base URL | `CHAT_BASE_URL` |
| `MEM0_LLM_MODEL` | Mem0 提取用模型名 | `CHAT_MODEL` |
| `BENCHMARK_EMBEDDING_*` | Embedding 配置（共用） | — |
| `CHAT_SERVER_API_KEY` | Server 鉴权密钥（Bearer token） | 不设则不鉴权 |
| `CHAT_USER_ID` | mem0 用户 ID | 默认 `xnne` |
| `CHAT_AGENT_ID` | mem0 Agent ID | 默认 `congyin` |
| `CLAIM_LLM_API_KEY` | Claim 提取 LLM 的 API key | `MEM0_LLM_API_KEY` |
| `CLAIM_LLM_BASE_URL` | Claim 提取 LLM 的 base URL | `MEM0_LLM_BASE_URL` |
| `CLAIM_LLM_MODEL` | Claim 提取模型名 | `MEM0_LLM_MODEL` |
| `NEO4J_CONTAINER` | Neo4j Docker 容器名 | `membench-neo4j-mem0` |
| `NEO4J_USER` | Neo4j 用户名 | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 密码 | `neo4jneo4j` |

### 在其他 FastAPI app 中挂载

```python
from fastapi import FastAPI
from memory_bench.server.router import router, state

app = FastAPI()
# 初始化 state.mem0 / state.openai_client / state.chat_model ...
app.include_router(router)
```

---

## 18. Chat CLI（`memory_bench/server/chat_cli.py`）

### 作用

终端交互式对话调试客户端，通过 HTTP 调用 Memory Chat Server，方便快速测试记忆增强功能，无需 curl 或等待前端接入。

### 特性

- 自动加载 `22_PERSONA_CANON.md` 作为 system prompt（聪音人设）
- `xnne>` / `congyin>` 提示符
- 上下文 in-memory，不持久化（一次对话完即消失）
- 支持 `--base-url` / `--system` / `--no-persona` / `--api-key`

### 调用示例

```bash
# 前提：先启动 server
just memory-chat-server

# 另一终端启动 CLI
just memory-chat-cli
just memory-chat-cli base_url=http://localhost:9090  # 自定义 server 地址

# 或直接调用
uv run memory_bench/server/chat_cli.py

# 跳过 persona 加载
uv run memory_bench/server/chat_cli.py --no-persona

# 追加额外 system prompt
uv run memory_bench/server/chat_cli.py --system "你是一个温柔的助手"
```

### 环境变量

| 环境变量 | 说明 | 回退 |
|----------|------|------|
| `CHAT_CLI_BASE_URL` | Server base URL | `http://localhost:8080` |
| `CHAT_SERVER_API_KEY` | Server 鉴权密钥 | 不设则不鉴权 |

### 退出方式

- 输入 `quit` 或 `exit`
- Ctrl+C / Ctrl+D

### 使用场景

- 快速测试记忆检索与写入
- 调试 persona 效果
- 验证 system prompt 调整
- 代替 curl 进行交互式调试

---

## 19. Claim Extractor（`memory_bench/server/claim_extractor.py`）

### 作用

实时 claim/entity 提取模块，是 `claimify_all.py` 的实时对应物。

`claimify_all.py` 依赖 `replay_mem0 export` 的完整 JSONL 格式（`point_id` / `hash` / `conv_id` 等），无法直接用于 Chat Server 的实时场景。`claim_extractor.py` 接收 `mem0.add()` 返回的轻量 results，通过 LLM 提取 claim/entity 记录，供 `graph_writer.py`（后续 Sub-2）写入 Neo4j。

### 核心函数

| 函数 | 说明 |
|------|------|
| `prepare_memory_items()` | 过滤 mem0 results，只保留 ADD/UPDATE 事件的非空文本，生成 prompt-ready items |
| `build_prompt()` | 构建简化版 claim extraction prompt（不需要 `point_id`/`hash`/`conv_id`） |
| `parse_llm_output()` | 解析 LLM 返回的 JSONL，逐行校验 record_type / predicate / domain / entity_type / confidence |
| `extract_claims()` | 主入口：prepare → prompt → LLM call → parse；任何失败返回 `[]`，永远不 raise |

### 设计决策

- **简化 prompt**：离线版需要完整 export payload，实时版只需 memory text + scene/character/user metadata
- **优雅降级**：LLM 返回空/格式错误 → 记日志 + 返回 `[]`，不阻塞对话
- **无 tag registry**：离线管线维护跨对话去重的 tag registry，实时模式跳过（轻微重复可接受，离线管线后续可 reconcile）
- **严格验证**：无效行静默跳过，confidence < 0.6 的 claim 不输出

### 与离线管线的关系

```
离线管线（batch）：
  replay_mem0 export → claimify_all.py → compiled_claims.py → claims_to_graph.py → ...

实时管线（realtime）：
  mem0.add() results → claim_extractor.py → graph_writer.py → Neo4j MERGE
```

两条管线共享相同的 predicates / entity_types / domains 白名单和 `claim_id` 格式，产出的 claim/entity 结构兼容。

### 使用方式

该模块不是独立 CLI，而是被 `router.py` 在 `_add_memory_sync()` 中调用（Sub-3 接入后）：

```python
from memory_bench.server.claim_extractor import extract_claims

records = extract_claims(
    openai_client=client,
    model="gpt-4o-mini",
    mem0_results=mem0_response["results"],
    scene_id="chill_ai_chat",
    user_id="xnne",
    agent_id="congyin",
)
# records: list of validated claim/entity dicts
```

---

## 20. Graph Writer（`memory_bench/server/graph_writer.py`）

### 作用

实时图谱写入模块，是离线管线 `claims_to_graph.py` → `graph_to_cypher.py` → `neo4j_apply_cypher.py` 的实时对应物。

接收 `claim_extractor.extract_claims()` 返回的 claim/entity records，在内存中完成 Graph IR 构建 + Cypher 生成，直接通过 `docker exec cypher-shell` 写入 Neo4j，不产生中间文件。

### 核心函数

| 函数 | 说明 |
|------|------|
| `write_to_neo4j()` | 主入口：records → split → build_graph → Cypher → docker exec；返回 `WriteResult` |
| `_run_cypher()` | 将 Cypher 文本管道到 `docker exec cypher-shell`，返回 `(ok, error)` |
| `_ensure_constraints()` | 幂等创建 `Node.id` 唯一约束 |
| `_docker_available()` | 检查 docker CLI 是否在 PATH 上 |

### 设计决策

- **复用离线模块**：`claims_to_graph.build_graph()` 构图 + `graph_to_cypher._build_node_merge()/_build_edge_merge()` 生成 Cypher，零重复逻辑
- **同执行路径**：与 `neo4j_apply_cypher.py` 一样用 `docker exec cypher-shell`，不引入 `neo4j` Python driver 新依赖
- **优雅降级**：Docker 不可用 / Neo4j 挂了 → 记日志 + 返回，不阻塞对话
- **幂等约束**：首次写入前自动 `CREATE CONSTRAINT ... IF NOT EXISTS`

### 返回值

`WriteResult` dataclass：

| 字段 | 类型 | 说明 |
|------|------|------|
| `nodes_written` | int | 成功执行的 node MERGE 数 |
| `edges_written` | int | 成功执行的 edge MERGE 数 |
| `nodes_skipped` | int | Cypher 生成失败的节点数 |
| `edges_skipped` | int | Cypher 生成失败的边数 |
| `cypher_ok` | bool | docker exec 是否成功 |
| `error` | str | 失败时的错误信息 |

### 使用方式

该模块不是独立 CLI，而是被 `router.py` 在 `_add_memory_sync()` 中调用（Sub-3 接入后）：

```python
from memory_bench.server.graph_writer import write_to_neo4j

result = write_to_neo4j(
    claim_records=records,
    user_id="xnne",
    container="membench-neo4j-mem0",
)
if not result.cypher_ok:
    log.warning("Graph write failed: %s", result.error)
```

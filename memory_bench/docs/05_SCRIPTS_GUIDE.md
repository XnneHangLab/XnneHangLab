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
  - `neo4j_clear.py`（清空 Neo4j 图数据，不重启容器）
  - `export_node_schema.py`（导出 Neo4j 图谱 Schema 参考文档）
  - `export_edge_schema.py`（导出 Neo4j 边 Schema 示例文档）
  - `latest_file.py`

- **工具模块**（非 CLI 主入口）
  - `bench_logger.py`（统一彩色日志）
  - `rate_limiter.py`（LLM API 令牌桶 + 并发控制）
  - `tag_registry.py`（tag 归一化与候选选择）

- **Memory Chat Server**（`memory_bench/server/`）
  - `startup.py`（初始化帮助函数 — 供外部 host app 调用）
  - `chat_server.py`（独立启动器 + CLI）
  - `neo4j_queries.py`（Neo4j Cypher 查询模板，与业务逻辑分离）
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
| `neo4j_clear.py` | 清空 Neo4j 图数据（不重启容器） |

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

- `startup.py` — 初始化帮助函数：`load_memory_bench_env()` / `resolve_memory_bench_config()` / `init_router_state()`。供 `chat_server.py` 和外部 host app 共用，避免重复代码。
- `router.py` — FastAPI APIRouter，包含端点、记忆逻辑和 graph pipeline 后台任务。可独立挂载到任意 FastAPI app。
- `chat_server.py` — 独立启动器：CLI 参数解析、env 加载（委托给 startup.py）、uvicorn 启动。
- `claim_extractor.py` — 从 mem0.add() 结果中提取 claim/entity 记录（LLM-based）。
- `graph_writer.py` — 将 claim 记录通过 Cypher MERGE 写入 Neo4j。

### 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | 记忆增强的 chat 接口（非 streaming） |
| `/v1/models` | GET | 兼容性端点 |
| `/health` | GET | 健康检查 |

> 当 router 挂载到 lab server（`package.memory_bench = true`）时，所有端点会加 `/memory` 前缀，例如：
> `12393/memory/v1/chat/completions`、`12393/memory/health`

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
| `ENABLE_GRAPH` | 启用实时 graph pipeline（`true`/`1`/`yes`） | `false`（默认不启用） |

### 在其他 FastAPI app 中挂载

`startup.py` 封装了初始化逻辑，外部 host app 直接调用即可，无需关心 mem0 / OpenAI client 的构建细节：

```python
from fastapi import FastAPI
from memory_bench.server.router import router as memory_router, state as memory_state
from memory_bench.server.startup import (
    load_memory_bench_env,
    resolve_memory_bench_config,
    init_router_state,
)

# 在 lifespan 里初始化（配置从 memory_bench/.env.benchmark 加载，与 host app 配置完全隔离）
load_memory_bench_env()
cfg = resolve_memory_bench_config()   # 可传 overrides={"enable_graph": True} 覆盖 env
init_router_state(memory_state, cfg)

app = FastAPI()
app.include_router(memory_router, prefix="/memory")
# → /memory/v1/chat/completions, /memory/health, ...
```

**lab server 集成方式（`src/lab/server.py`）：**

在 `config/lab.toml` 中开启：

```toml
[package]
memory_bench = true
```

Graph pipeline 通过 `memory_bench/.env.benchmark` 控制（不在 lab.toml 里配）：

```bash
# memory_bench/.env.benchmark
ENABLE_GRAPH=true
```

配置隔离保证：lab.toml 只决定是否 enable，不注入任何 memory_bench 配置值。

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

## 20. Neo4j Clear（`memory_bench/scripts/neo4j_clear.py`）

### 作用

清空 Neo4j 图数据（所有节点和关系），无需重启容器。

相比 `clean-and-restart-neo4j`（删除 volume + 重启容器），此脚本：
- **更快**：无需 sleep 等待容器重启（节省 20-30 秒）
- **更温和**：只清空数据，保留容器状态和配置
- **支持多容器**：可通过 `--container` 指定目标 Neo4j 实例

### 调用示例

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

### 参数

| 参数 | 说明 |
|------|------|
| `--container` | Neo4j Docker 容器名（默认：`membench-neo4j-mem0`） |
| `--user` | Neo4j 用户名（默认：`neo4j`） |
| `--password` | Neo4j 密码（默认：`neo4jneo4j`） |
| `--keep-constraints` | 保留现有 constraints 和 indexes |
| `--dry-run` | 只打印命令，不执行 |

### 环境变量

从 `memory_bench/.env.benchmark` 读取（可选）：

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `NEO4J_CONTAINER` | Neo4j 容器名 | `membench-neo4j-mem0` |
| `NEO4J_USER` | Neo4j 用户名 | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 密码 | `neo4jneo4j` |

优先级：CLI 参数 > 环境变量 > 脚本默认值。

### 执行逻辑

1. 加载 `.env.benchmark`（如果存在）
2. 可选：Drop constraints（除非 `--keep-constraints`）
3. 可选：Drop indexes（除非 `--keep-constraints`）
4. 执行 `MATCH (n) DETACH DELETE n;` 清空所有数据

### 使用场景

- 测试前清空图数据（配合 `just clean-neo4j`）
- 重新跑离线管线前重置 Neo4j
- 调试实时管线时快速重置

---

## 21. Graph Writer（`memory_bench/server/graph_writer.py`）

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

- **复用离线模块**：`claims_to_graph.build_graph()` 构图 + `graph_to_cypher.build_node_merge()/build_edge_merge()` 生成 Cypher，零重复逻辑
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

---

## 21. 离线管线 vs 实时管线 — 差异与边界行为

### 工作流对比

```
【离线管线】（用于 benchmark replay）
┌─────────────────────────────────────────────────────────────────────────┐
│  章节原文 → [annotate_all] → events/by_chapter → [compile_events]      │
│              (LLM #1) ↑ 增量检查：by_chapter/*.jsonl 存在则 skip       │
│                                    ↓                                    │
│                          events/compiled/all.jsonl                      │
│                                    ↓                                    │
│  ← [replay_mem0 ingest] → state/checkpoint.json (增量：checkpoint)     │
│              ↓                                                          │
│  [replay_mem0 export] → logs/replay_mem0/export_*.jsonl                │
│              ↓                                                          │
│  [claimify_all] → claims/by_conv/*.jsonl (LLM #3)                       │
│              ↑ 增量检查：by_conv/*.jsonl 存在则 skip                    │
│              ↓                                                          │
│  [compiled_claims.py] → claims/compiled/*.jsonl                         │
│              ↓                                                          │
│  [mem0_to_graph] → logs/replay_mem0/graphify/*.jsonl                    │
│              ↑ 增量：state/graphify/state.sqlite                        │
│              ↓                                                          │
│  [graph_to_cypher] → logs/*/neo4j/*.cypher                              │
│              ↓                                                          │
│  [neo4j_apply_cypher] → Neo4j (MERGE 幂等)                              │
└─────────────────────────────────────────────────────────────────────────┘

【实时管线】（用于 Chat Server）
┌─────────────────────────────────────────────────────────────────────────┐
│  用户对话 → router.py → mem0.add() → mem0 results                       │
│                                    ↓                                    │
│  [claim_extractor] → claim records (内存，不持久化)                      │
│              ↓                                                          │
│  [graph_writer] → Cypher MERGE (内存生成，直接执行)                      │
│              ↓                                                          │
│  Neo4j (图数据持久化)                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 关键差异

| 维度 | 离线管线 | 实时管线 |
|------|----------|----------|
| **中间产物** | 全部持久化（JSONL + Cypher 文件） | 不持久化（内存中直接执行） |
| **Claim 提取** | `claimify_all.py` → `data/claims/by_conv/*.jsonl` | `claim_extractor.py` → 内存 records |
| **图谱构建** | `claims_to_graph.py` → `logs/claims/graphify/*.jsonl` | `graph_writer.py` → 内存 Graph IR |
| **Cypher 生成** | `graph_to_cypher.py` → `logs/*/neo4j/*.cypher` | `graph_writer.py` → 内存 Cypher 字符串 |
| **Neo4j 写入** | `neo4j_apply_cypher.py` 执行文件 | `graph_writer.py` 直接 `docker exec` |

### 增量检查点总览

| 步骤 | 脚本 | 增量依据 | 跳过条件 |
|------|------|---------|---------|
| 1 | `annotate_all.py` | `data/events/by_chapter/{conv_id}.jsonl` | 文件存在且非空 |
| 2 | `replay_mem0.py ingest` | `state/mem0_*.checkpoint.json` | checkpoint 已记录该事件 |
| 3 | `replay_mem0.py export` | 无 | 总是导出当前快照 |
| 4 | `claimify_all.py` | `logs/replay_mem0/export_*.jsonl` + `data/claims/by_conv/{conv_id}.jsonl` | export 存在 + by_conv 存在 |
| 5 | `compiled_claims.py` | `data/claims/compiled/*.jsonl` | 文件存在且 `--force` 未指定 |
| 6 | `mem0_to_graph.py add` | `state/graphify/state.sqlite` | 已处理的 export 文件跳过 |
| 7 | `graph_to_cypher.py` | 无 | 总是生成新 Cypher |
| 8 | `neo4j_apply_cypher.py` | 无 | MERGE 幂等，重复执行安全 |

### 快速测试入口（justfile）

| 命令 | 清理范围 | 重跑范围 | 适用场景 |
|------|---------|---------|---------|
| `mem0-run-from-annotate` | 全部清空 | 全部重跑 | 第一次跑通全流程 |
| `mem0-run-from-ingest` | 保留 events | ingest 及之后重跑 | 调试 ingest/export/claimify |
| `mem0-run-from-claim` | 保留 events + export | claimify 及之后重跑 | 调试 claim 提取/图谱构建 |
| `mem0-run-real-time` | qdrant + Neo4j | 实时管线 | 测试 Chat Server |

### 清理边界

**问：我胡乱清 logs 会不会导致下次再启动 server 时 graph 被清空？**

**答：不会。** Neo4j 图数据存储在 Docker volume（`memory_bench/neo4j-data/mem0/data`），与 logs 目录完全独立。

- 清理 `memory_bench/logs/` → 只删除离线管线的中间产物，**不影响 Neo4j**
- 清理 `memory_bench/state/` → 只删除 checkpoint/state.sqlite/qdrant，**不影响 Neo4j**
- 清理 `memory_bench/data/claims/` → 只删除离线管线的 claims 产物，**不影响 Neo4j**
- 清理 `memory_bench/neo4j-data/` → **会清空 Neo4j**，需要重启容器

**问：实时管线的中间产物在哪？清理会影响吗？**

**答：实时管线没有中间产物。** `claim_extractor.py` 和 `graph_writer.py` 都在内存中完成工作，直接执行 Cypher MERGE 写入 Neo4j。清理任何文件都不会影响实时管线的历史写入。

**问：清理 qdrant_storage 会不会影响已写入 Neo4j 的图？**

**答：不会。** qdrant_storage 是 mem0 的向量检索存储（用于记忆检索），Neo4j 是图谱存储（用于语义关系）。清理 qdrant 只会让 mem0 "失忆"（检索不到历史记忆），但 Neo4j 中的图数据不受影响。

### 增量 Apply 语义

**问：如果旧文件被清空，只剩下新增文件去 apply，会不会导致图被覆盖？**

**答：不会。** 两条管线都使用 Cypher `MERGE` 而非 `CREATE`：

- `graph_to_cypher.py` 生成 `MERGE (n:Node {id: $id}) ON CREATE SET ...`
- `neo4j_apply_cypher.py` 执行时，已存在的节点/边会被跳过（幂等）
- `graph_writer.py` 同样使用 `MERGE`，实时写入也是幂等的

**因此**：
- 清空旧文件后只 apply 新文件 → **只会新增，不会覆盖/删除已有数据**
- 重复 apply 同一份文件 → **幂等，不会重复创建**
- 离线管线 + 实时管线混用 → **兼容，都写入同一张图**

### 基础清理原语（justfile）

| 命令 | 清理范围 |
|------|--------|
| `clean-neo4j` | Neo4j 图数据（Docker volume） |
| `clean-bench-logs` | 整个 `logs/` 目录 |
| `clean-bench-state` | 整个 `state/` 目录（checkpoint / state.sqlite） |
| `clean-bench-events` | `data/events/` |
| `clean-bench-claims` | `data/claims/` |
| `clean-realtime` | qdrant_storage + Neo4j（实时管线专用） |

---

## 21. Neo4j Schema 导出（export_node_schema.py）

> **用途**：导出 Neo4j 图谱的完整 Schema 参考文档，包括节点示例和关系示例。
> **输出**：`memory_bench/docs/06_NODE_SCHEMA_REFERENCE.md`

### 调用示例

```bash
# 导出 Markdown 格式（默认）
uv run memory_bench/scripts/export_node_schema.py

# 导出 JSON 格式
uv run memory_bench/scripts/export_node_schema.py --format json

# 自定义输出路径
uv run memory_bench/scripts/export_node_schema.py --output /tmp/schema.md

# 指定 Neo4j 容器
uv run memory_bench/scripts/export_node_schema.py --container my-neo4j-container
```

### 输入

- **Neo4j 容器**：从 `.env.benchmark` 读取 `NEO4J_CONTAINER`（默认：`membench-neo4j-mem0`）
- **认证信息**：从 `.env.benchmark` 读取 `NEO4J_USER` 和 `NEO4J_PASSWORD`

### 输出

**Markdown 格式**（`06_NODE_SCHEMA_REFERENCE.md`）：

```markdown
# Neo4j NODE 图谱 Schema 参考

## 节点示例（按 ID 前缀分类，每类一个完整示例）

### MemoryItem
- **ID**: mem:59484ed1e8b9edf03c71c86146e8fc88
- **Name**: [User] 会使用一个小杯子来给茶散热。 #59484ed1
- **Display**: [User] 会使用一个小杯子来给茶散热。 #59484ed1
- **Properties**:
```json
{
  "point_id": "74bcb98f-4b74-4f0a-988b-0d6618061c14",
  "data": "[User] 会使用一个小杯子来给茶散热。",
  "created_at": "2026-02-27T04:08:26.369766-08:00",
  ...
}
```

## 关系示例（每个类型一个完整示例）

| 关系类型 | 源节点 | 源节点 ID | 目标节点 | 目标节点 ID |
|----------|--------|-----------|----------|-------------|
| ABOUT | Node | claim:... | Node | topic:... |
| ACTOR | Node | agent:congyin | Node | char:congyin |
| OWNS_MEMORY | Character | char:xnne | MemoryItem | mem:... |
...
```

**JSON 格式**：

```json
{
  "generated_at": "2026-02-27T21:44:11.900543+08:00",
  "neo4j_container": "membench-neo4j-mem0",
  "node_examples": [
    {
      "node_type": "MemoryItem",
      "id": "mem:xxx",
      "name": "...",
      "display": "...",
      "all_props": {...}
    }
  ],
  "edge_examples": [...]
}
```

### 节点分类规则

脚本根据节点 ID 的前缀自动分类：

| ID 前缀 | 节点类型 |
|---------|---------|
| `mem:` | MemoryItem |
| `claim:` | Claim |
| `topic:` | Topic |
| `char:` | Character |
| `user:` | User |
| `agent:` | Agent |
| `scene:` | Scene |
| `conv:` | Conversation |
| `dom:` | Domain |
| `pred:` | Predicate |
| 其他 | Other |

### 使用场景

1. **验证图谱结构**：检查节点和关系是否符合预期
2. **调试数据问题**：查看具体节点的完整属性
3. **文档生成**：自动生成最新的 Schema 参考文档
4. **离线/实时管线对比**：分别导出两个管线的 Schema，确保一致

### 常见问题

**问：为什么有些节点的 Properties 是空字典？**

**答**：可能该节点只有 `id`、`name`、`display` 等基础属性，没有其他自定义属性。

**问：导出的关系示例里为什么只有 12 个？**

**答**：`export_node_schema.py` 对每个关系类型只保留一个示例（去重），避免文档过长。完整的关系数据可以通过 Neo4j Browser 直接查询。

**问：JSON 解析失败怎么办？**

**答**：脚本内置了智能 CSV 解析器，处理 Neo4j 输出的嵌套 JSON。如果仍有问题，检查 Neo4j 版本是否兼容，或手动运行查询验证：

```cypher
MATCH (n)
WHERE n.id IS NOT NULL
WITH labels(n)[0] AS label, n
WITH label, collect(n)[0] AS example
RETURN label, properties(example) AS all_props
LIMIT 1;
```


---

## 22. Neo4j 边 Schema 导出（export_edge_schema.py）

> **用途**：导出 Neo4j 图谱中"边"的完整示例文档，分别按 **边 ID 前缀** 和 **关系类型** 去重保留每类一个示例。
> **输出**：`memory_bench/docs/08_EDGE_SCHEMA_REFERENCE.md`

### 调用示例

```bash
# 导出 Markdown 格式（默认）
uv run memory_bench/scripts/export_edge_schema.py

# 导出 JSON 格式
uv run memory_bench/scripts/export_edge_schema.py --format json

# 自定义输出路径
uv run memory_bench/scripts/export_edge_schema.py --output /tmp/edge-schema.md

# 指定 Neo4j 容器
uv run memory_bench/scripts/export_edge_schema.py --container my-neo4j-container
```

### 输入

- **Neo4j 容器**：从 `.env.benchmark` 读取 `NEO4J_CONTAINER`（默认：`membench-neo4j-mem0`）
- **认证信息**：从 `.env.benchmark` 读取 `NEO4J_USER` 和 `NEO4J_PASSWORD`

### 输出结构

Markdown 文档包含两个章节：

1. `## 边示例（按 ID 前缀分类，每类一个完整示例）`
2. `## 关系示例（每个类型一个完整示例）`
3. 文档底部还会追加同名章节的**汇总表格**：`| 关系类型 | 源节点 | 源节点 ID | 目标节点 | 目标节点 ID |`

其中每条示例都包含：

- `Edge Type`
- `Source`（src label + src id）
- `Target`（dst label + dst id）
- `Relationship (raw)`（Neo4j relationship 完整对象）
- `Edge Properties`（`properties(r)` 结果）

### 去重规则

- **按边 ID 前缀**：基于 `r.id` 的 `:` 前缀分组，每组仅保留一个完整样例
- **按关系类型**：基于 `type(r)` 分组，每种关系仅保留一个完整样例

### 使用场景

1. **排查边字段一致性**：快速检查某类边的属性是否完整（如 `src/dst/predicate/domain`）
2. **校验命名规范**：检查 `r.id` 的前缀分布是否符合预期
3. **联调实时/离线写图**：确认不同写入链路产出的边结构一致

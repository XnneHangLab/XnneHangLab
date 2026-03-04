# Memory Bench 脚本指南

> **路由索引文件** — 本文档作为脚本目录的入口，讲述管线整体流程和 Server 架构。
> 每个脚本的详细说明请参阅 [`script_guide/`](./script_guide/) 下的独立文档。

---

## 目录结构

```
docs/
├── 05_SCRIPTS_GUIDE.md          # 本文件（路由索引）
├── script_guide/                 # 脚本详情目录
│   ├── build_index.md
│   ├── annotate_all.md
│   ├── compile_events.md
│   ├── replay_mem0.md
│   ├── claimify_all.md
│   ├── compiled_claims.md
│   ├── mem0_to_graph.md
│   ├── claims_to_graph.md
│   ├── graph_to_cypher.md
│   ├── neo4j_apply_cypher.md
│   ├── latest_file.md
│   ├── neo4j_clear.md
│   ├── export_node_schema.md
│   ├── export_edge_schema.md
│   ├── startup.md
│   ├── chat_server.md
│   ├── chat_router.md
│   ├── conversation_store.md
│   ├── claim_extractor.md
│   ├── graph_writer.md
│   ├── neo4j_queries.md
│   ├── chat_cli.md
│   ├── bench_logger.md
│   ├── rate_limiter.md
│   └── tag_registry.md
└── ...
```

---

## 一、离线管线（Offline Pipeline）

离线管线用于 benchmark replay，将原始章节文本逐步转换为 Neo4j 图谱数据。

### 1.1 数据构建流程

```
章节原文 → [build_index] → index.json
              ↓
    [annotate_all] → events/by_chapter/*.jsonl
              ↓
   [compile_events] → events/compiled/all.jsonl
```

**相关脚本**：
- [`build_index.md`](./script_guide/build_index.md) — 生成章节索引
- [`annotate_all.md`](./script_guide/annotate_all.md) — LLM 标注为 events
- [`compile_events.md`](./script_guide/compile_events.md) — 拼接为全量 JSONL

### 1.2 Mem0 回放流程

```
events/compiled/all.jsonl
         ↓
[replay_mem0 ingest] → Mem0（Qdrant 存储）
         ↓
[replay_mem0 export] → logs/replay_mem0/export_*.jsonl
```

**相关脚本**：
- [`replay_mem0.md`](./script_guide/replay_mem0.md) — ingest / probe / export 三合一

### 1.3 Claim 抽取流程

```
export_*.jsonl
     ↓
[claimify_all] → claims/by_conv/*.jsonl
     ↓
[compiled_claims] → claims/compiled/*.jsonl
```

**相关脚本**：
- [`claimify_all.md`](./script_guide/claimify_all.md) — LLM 抽取 claim/entity
- [`compiled_claims.md`](./script_guide/compiled_claims.md) — 汇总去重

### 1.4 图谱导出流程

```
claims/compiled/*.jsonl  +  export_*.jsonl
           ↓
  [mem0_to_graph]  ──┐
  [claims_to_graph] ─┤
           ↓         ↓
    graph_nodes/edges JSONL
           ↓
   [graph_to_cypher] → *.cypher
           ↓
[neo4j_apply_cypher] → Neo4j
```

**相关脚本**：
- [`mem0_to_graph.md`](./script_guide/mem0_to_graph.md) — mem0 export → graph IR
- [`claims_to_graph.md`](./script_guide/claims_to_graph.md) — claims → graph IR
- [`graph_to_cypher.md`](./script_guide/graph_to_cypher.md) — graph IR → Cypher
- [`neo4j_apply_cypher.md`](./script_guide/neo4j_apply_cypher.md) — Cypher → Neo4j

### 1.5 辅助工具

| 脚本 | 说明 |
|------|------|
| [`latest_file.md`](./script_guide/latest_file.md) | 获取最新文件路径（justfile 集成） |
| [`neo4j_clear.md`](./script_guide/neo4j_clear.md) | 清空 Neo4j 数据（不重启容器） |
| [`export_node_schema.md`](./script_guide/export_node_schema.md) | 导出节点 Schema 参考 |
| [`export_edge_schema.md`](./script_guide/export_edge_schema.md) | 导出边 Schema 参考 |

### 1.6 完整执行顺序

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

# 6) graph → cypher
just mem0-to-graph
just claims-to-graph
just graph-to-cypher

# 7) 导入 Neo4j
just neo4j-apply-cypher
```

> 工作流编排由 `justfile` 管理，详见仓库根目录 `justfile`。

---

## 二、实时管线（Real-time Pipeline）

实时管线用于 Chat Server，在用户对话过程中实时提取 claim 并写入 Neo4j。

### 2.1 架构概览

```
AIChat 客户端
     ↓  POST /memory/chat
chat_router.py
     ├─ 读取 conversation_store（历史对话）
     ├─ 拼接 system prompt（prompts/）
     ├─ 调用 LLM → 生成回复
     ├─ 保存对话到 conversation_store
     └─ [可选] 实时图谱写入
            ├─ claim_extractor → 提取 claim/entity
            └─ graph_writer → Cypher MERGE → Neo4j
```

### 2.2 核心模块

| 模块 | 说明 |
|------|------|
| [`chat_router.md`](./script_guide/chat_router.md) | FastAPI router，`/memory/chat` 端点 |
| [`chat_server.md`](./script_guide/chat_server.md) | 独立启动器 + CLI |
| [`conversation_store.md`](./script_guide/conversation_store.md) | 对话 JSONL 持久化（按日期分文件） |
| [`startup.md`](./script_guide/startup.md) | 初始化帮助函数（env 加载、配置解析） |

### 2.3 实时图谱写入

| 模块 | 说明 |
|------|------|
| [`claim_extractor.md`](./script_guide/claim_extractor.md) | 实时 claim 提取（LLM-based） |
| [`graph_writer.md`](./script_guide/graph_writer.md) | Cypher 生成 + Neo4j 写入 |
| [`neo4j_queries.md`](./script_guide/neo4j_queries.md) | Cypher 查询模板（与业务逻辑分离） |

### 2.4 调试工具

| 工具 | 说明 |
|------|------|
| [`chat_cli.md`](./script_guide/chat_cli.md) | 终端交互式对话客户端 |

### 2.5 启动方式

```bash
# 启动 Server（默认端口 8080）
just memory-chat-server

# 启动 Server（自定义端口）
uv run memory_bench/server/chat_server.py --port 9090

# 启用实时图谱写入
uv run memory_bench/server/chat_server.py --enable-graph

# 启动 CLI 调试客户端
just memory-chat-cli
```

---

## 三、工具模块

这些模块不是独立 CLI，而是被其他脚本复用的工具库。

| 模块 | 说明 |
|------|------|
| [`bench_logger.md`](./script_guide/bench_logger.md) | 统一彩色日志 |
| [`rate_limiter.md`](./script_guide/rate_limiter.md) | LLM API 令牌桶 + 并发控制 |
| [`tag_registry.md`](./script_guide/tag_registry.md) | tag 归一化与候选选择 |

---

## 四、离线管线 vs 实时管线 — 对比

| 维度 | 离线管线 | 实时管线 |
|------|----------|----------|
| **用途** | benchmark replay | 真实用户对话 |
| **中间产物** | 全部持久化（JSONL + Cypher 文件） | 不持久化（内存中直接执行） |
| **Claim 提取** | `claimify_all.py` → 文件 | `claim_extractor.py` → 内存 |
| **图谱构建** | `claims_to_graph.py` → 文件 | `graph_writer.py` → 内存 |
| **Neo4j 写入** | `neo4j_apply_cypher.py` 执行文件 | `graph_writer.py` 直接 `docker exec` |
| **对话存储** | 无（一次性回放） | `conversation_store.py`（JSON 文件） |

---

## 五、增量检查点总览

| 步骤 | 脚本 | 增量依据 | 跳过条件 |
|------|------|---------|---------|
| 1 | `annotate_all.py` | `data/events/by_chapter/{conv_id}.jsonl` | 文件存在且非空 |
| 2 | `replay_mem0 ingest` | `state/mem0_*.checkpoint.json` | checkpoint 已记录该事件 |
| 3 | `replay_mem0 export` | 无 | 总是导出当前快照 |
| 4 | `claimify_all.py` | `data/claims/by_conv/{conv_id}.jsonl` | by_conv 文件存在 |
| 5 | `compiled_claims.py` | `data/claims/compiled/*.jsonl` | 文件存在且 `--force` 未指定 |
| 6 | `mem0_to_graph.py add` | `state/graphify/state.sqlite` | 已处理的 export 文件跳过 |
| 7 | `graph_to_cypher.py` | 无 | 总是生成新 Cypher |
| 8 | `neo4j_apply_cypher.py` | 无 | MERGE 幂等，重复执行安全 |

---

## 六、快速参考

### 清理命令

| 命令 | 清理范围 |
|------|--------|
| `clean-neo4j` | Neo4j 图数据（Docker volume） |
| `clean-bench-logs` | 整个 `logs/` 目录 |
| `clean-bench-state` | 整个 `state/` 目录 |
| `clean-bench-events` | `data/events/` |
| `clean-bench-claims` | `data/claims/` |
| `clean-realtime` | qdrant_storage + Neo4j（实时管线专用） |

### 常见场景

| 场景 | 命令 |
|------|------|
| 第一次跑通全流程 | `just mem0-run-from-annotate` |
| 调试 ingest/export | `just mem0-run-from-ingest` |
| 调试 claim 提取 | `just mem0-run-from-claim` |
| 测试实时管线 | `just mem0-run-real-time` |

---

## 七、相关文档

- [`00_DOC_MAP.md`](./00_DOC_MAP.md) — 文档地图
- [`06_NODE_SCHEMA_REFERENCE.md`](./06_NODE_SCHEMA_REFERENCE.md) — Neo4j 节点 Schema
- [`08_EDGE_SCHEMA_REFERENCE.md`](./08_EDGE_SCHEMA_REFERENCE.md) — Neo4j 边 Schema
- [`30_TYPING_DESIGN.md`](./30_TYPING_DESIGN.md) — 类型设计
- [`40_ANCHORS_AND_TEMPLATES.md`](./40_ANCHORS_AND_TEMPLATES.md) — 锚点与模板

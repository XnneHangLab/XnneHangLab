# graphify_export 规范草案

## 1. 背景与定位

当前 mem0 快照导出由 `memory_bench/scripts/replay_mem0.py export` 生成，输出为 JSONL。建议新增一个后处理脚本 `graphify_export`，消费该 JSONL 并产出图谱友好的节点/边结构，保持与 `memory_bench/scripts` 现有命名与参数风格一致。

> **范围约束（V0）**：本规范仅覆盖第一层 metadata/归属图，不包含语义实体抽取、语义关系推断、taxonomy 建模。

V0 仅包含以下节点类型：

- `MemoryItem`
- `User`
- `Agent`
- `Conversation`
- `Scene`
- `Character`

V0 仅包含上述节点之间的固定元数据关系（见第 3.3 节）。

## 2. 输入契约（Input Contract）

### 2.1 输入文件

- 格式：UTF-8 JSONL（每行一个 JSON object）
- 默认来源：`memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl`
- 可通过 `--input` 覆盖

### 2.2 单行记录 schema（来自现有 export）

每行顶层字段：

- `id` (string | number)：向量库 point id
- `payload` (object | null)：Mem0/Qdrant payload
- `collection` (string)：collection 名称
- `isolation` ("global" | "per_chapter")：隔离模式
- `exported_at` (string, ISO-8601 UTC)：本次导出时间

`payload` 常见 key（按现有样例 + 代码行为）：

- `scene_id` (string)
- `character_id` (string)
- `conv_id` (string)
- `user_id` (string)
- `agent_id` (string)
- `data` (string)
- `hash` (string)
- `created_at` (string, ISO-8601)

> 说明：`payload` 由上游 Mem0 写入，导出阶段不做强约束，因此 graphify 需要容忍缺失字段与额外字段。

### 2.3 输入校验建议

- 必须是合法 JSONL；空行可记 warning 并跳过（统计到 `skipped_empty_line`）
- 顶层对象缺 `id`/`collection`/`isolation`/`exported_at` 时记 warning 并跳过（统计到 `skipped_missing_top_level`）
- `payload` 为 `null` 时跳过并统计 `skipped_null_payload`

### 2.4 记录唯一键（processed_key）

用于增量 `add` 模式的去重键，优先级如下：

1. `payload.hash`（存在且非空时）
2. 顶层 `id`（字符串化后）

记为：`processed_key`。

> 一致性要求：`processed_key` 与 `MemoryItem.id` 的主键选择必须使用同一套优先级规则（`payload.hash` 优先，否则 top-level `id`），避免增量去重与节点 ID 不一致。

- `state.sqlite` 中将持久化 `processed_key`。
- `add` 仅处理 `processed_key` 尚未出现的记录。
- 若两者都不可用，则该记录跳过并计入 `skipped_missing_processed_key`。

## 3. 输出契约（Output Contract）

建议输出目录：`memory_bench/logs/replay_mem0/graphify/`

建议输出 3 类文件：

1. `graph_nodes_YYYYMMDD_HHMMSS.jsonl`
2. `graph_edges_YYYYMMDD_HHMMSS.jsonl`
3. `graphify_report_YYYYMMDD_HHMMSS.json`

可选输出（`--format jsonl+csv`）：

4. `graph_nodes_YYYYMMDD_HHMMSS.csv`
5. `graph_edges_YYYYMMDD_HHMMSS.csv`

### 3.1 nodes JSONL（必选）

每行一个 node：

- `id` (string, required)
- `labels` (string[], required)
- `props` (object, required)

约束：

- `labels` 至少一个标签，V0 推荐主标签集合：
  - `MemoryItem`
  - `User`
  - `Agent`
  - `Conversation`
  - `Scene`
  - `Character`
- `props` 中可包含业务字段（如 `user_id`、`scene_id`、`payload_hash`、`exported_at` 等）。

### 3.2 edges JSONL（必选）

每行一个 edge：

- `id` (string, optional but recommended)
- `type` (string, required)
- `src` (string, required)
- `dst` (string, required)
- `props` (object, required)

约束：

- V0 应输出稳定 `id`（推荐，见第 3.4 节）。
- `type` 必须来自第 3.3 节固定关系集合。
- `edges.props` 推荐包含 provenance 字段（如 `processed_key`、`source_point_id`、`exported_at`、`created_at`），用于审计与回放。

### 3.3 V0 固定关系类型集合（必须）

V0 第一层仅允许以下关系类型与方向：

1. `OWNS_MEMORY`
   - `src=User` → `dst=MemoryItem`
2. `TARGETS_AGENT`
   - `src=MemoryItem` → `dst=Agent`
3. `FROM_CONV`
   - `src=MemoryItem` → `dst=Conversation`
4. `IN_SCENE`
   - `src=MemoryItem` → `dst=Scene`
5. `HAS_CHARACTER`
   - `src=MemoryItem` → `dst=Character`
6. `CONV_IN_SCENE`
   - `src=Conversation` → `dst=Scene`
7. `CONV_HAS_CHARACTER`
   - `src=Conversation` → `dst=Character`
8. `USER_IN_SCENE`
   - `src=User` → `dst=Scene`
9. `AGENT_IS_CHARACTER`
   - `src=Agent` → `dst=Character`

> 说明：以上为第一层固定集合。V0 禁止新增语义关系类型。

### 3.4 稳定 ID 方案（必须，保证幂等）

为保证重复运行与重复导入不产生重复节点/边，V0 采用可重算的稳定 ID。

#### 3.4.1 节点 ID

- `MemoryItem`：`mem:{memory_key}`
  - `memory_key = payload.hash`（优先）
  - 若 `payload.hash` 缺失，`memory_key = point:{id}`
  - 该优先级与第 2.4 节 `processed_key` 必须严格一致
- `User`：`user:{user_id}`
- `Agent`：`agent:{agent_id}`
- `Conversation`：`conv:{conv_id}`
- `Scene`：`scene:{scene_id}`
- `Character`：`char:{character_id}`

若某实体主键缺失，则不生成对应节点，并在 report 的 skipped 计数中记录。

#### 3.4.2 边 ID

推荐强制输出边 `id`，格式：

`edge:{type}:{src}:{dst}`

如：`edge:OWNS_MEMORY:user:chill_ai_chat:congyin:mem:d82ae1eafae11287f949b39cb11dd939`

该规则保证同一关系重复导入时可去重（图数据库可据此 MERGE）。

### 3.5 report JSON（必选）

- `input_path`
- `nodes_path`
- `edges_path`
- `records_total`
- `records_valid`
- `records_skipped`
- `skipped_empty_line`
- `skipped_invalid_json`
- `skipped_missing_top_level`
- `skipped_null_payload`
- `skipped_missing_processed_key`
- `skipped_missing_memory_id`
- `nodes_total`
- `edges_total`
- `nodes_by_label` (object)
- `edges_by_type` (object)
- `duration_ms`
- `warnings` (array[string])
- `edge_props_provenance_recommended` (array[string], 建议值：`["processed_key","source_point_id","exported_at","created_at"]`)

其中：

- `records_skipped` = 所有 `skipped_*` 计数之和。
- `nodes_by_label` 示例：`{"MemoryItem": 1200, "User": 12}`。
- `edges_by_type` 示例：`{"OWNS_MEMORY": 1200, "FROM_CONV": 1190}`。

## 4. CLI 草案

脚本建议：`memory_bench/scripts/graphify_export.py`

```bash
uv run python memory_bench/scripts/graphify_export.py dry-run \
  --input memory_bench/logs/replay_mem0/export_20260218_031242.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --state-db memory_bench/state/graphify/state.sqlite \
  --format jsonl
```

### 4.1 子命令（必须）

1. `reset`
   - 清空/重建 `state.sqlite`（processed_key 集）
   - 可选清理输出目录中的 graphify 产物
2. `add`
   - 增量处理输入 JSONL
   - 基于 `state.sqlite` 跳过已处理记录
3. `dry-run`
   - 执行与 `add` 相同的解析、校验、映射与统计
   - 不写 nodes/edges 文件，不写入 `state.sqlite`

### 4.2 参数建议

- `--input` (str, `add`/`dry-run` 必需)：export JSONL 输入
- `--out-dir` (str, default=`memory_bench/logs/replay_mem0/graphify`)
- `--state-db` (str, default=`memory_bench/state/graphify/state.sqlite`)
- `--prefix` (str, default=`graph`)
- `--format` (choices=`jsonl`, `jsonl+csv`)
- `--strict` (flag)：严格模式，遇到 schema 问题直接失败
- `--reset-output` (flag, 仅 `reset`)：同时清理输出目录

### 4.3 add 的增量机制（必须）

- `state.sqlite` 至少包含一张表（示例）：
  - `processed_records(processed_key TEXT PRIMARY KEY, processed_at TEXT NOT NULL, source_file TEXT, source_line INTEGER)`
- `add` 对每条记录计算 `processed_key`（见 2.4 节）：
  - 若已存在：跳过（计入 `skipped_already_processed`）
  - 若不存在：执行映射并在成功后写入 `processed_key`
- `add` 失败重试时，已成功写入 state 的记录不会重复处理。

### 4.4 返回码建议

- `0`：成功
- `1`：输入不可读/JSONL 非法/schema 严重错误

## 5. 目录与命名建议（贴合仓库惯例）

- **代码位置**：`memory_bench/scripts/graphify_export.py`
  - 与 `replay_mem0.py`、`compile_events.py` 同层，符合“单文件脚本 + argparse + main()”习惯。
- **日志/产物位置**：`memory_bench/logs/replay_mem0/graphify/`
  - 延续 replay 相关日志在 `memory_bench/logs/replay_mem0/` 下管理的结构。
- **命名风格**：
  - 脚本：`snake_case.py`
  - 子命令可后续扩展为 `graphify_export.py build|stats`
  - 输出文件：`{kind}_YYYYMMDD_HHMMSS.{jsonl|json}` 时间戳命名，便于追溯。

## 6. 实施建议（最小可用版本）

第一版可仅实现：

1. 读取 export JSONL
2. 将每条 payload 映射为 `MemoryItem` + 归属节点（User/Agent/Conversation/Scene/Character）
3. 严格按第 3.3 节生成固定关系类型与方向
4. 输出 nodes/edges/report 三文件（可选 CSV）
5. 落地 `state.sqlite` 的 processed_key 增量机制（reset/add/dry-run）
6. 使用 `bench_logger` 的 `logger.bind(group="memory")` 输出进度与统计

---

## 7. V0 示例

以下示例使用一条 export 记录（占位值）：

```json
{"id":"074bbc5d-2eb3-4859-80db-c4f898e8820c","payload":{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"ch9998","user_id":"chill_ai_chat:congyin","agent_id":"congyin","data":"很喜欢夏目漱石","hash":"d82ae1eafae11287f949b39cb11dd939","created_at":"2026-02-17T19:12:27.733459-08:00"},"collection":"memory_bench_global","isolation":"global","exported_at":"2026-02-18T03:12:42Z"}
```

### 7.1 nodes.jsonl 示例行

```json
{"id":"mem:d82ae1eafae11287f949b39cb11dd939","labels":["MemoryItem"],"props":{"point_id":"074bbc5d-2eb3-4859-80db-c4f898e8820c","payload_hash":"d82ae1eafae11287f949b39cb11dd939","data":"很喜欢夏目漱石","created_at":"2026-02-17T19:12:27.733459-08:00","collection":"memory_bench_global","isolation":"global","exported_at":"2026-02-18T03:12:42Z"}}
{"id":"user:chill_ai_chat:congyin","labels":["User"],"props":{"user_id":"chill_ai_chat:congyin"}}
{"id":"agent:congyin","labels":["Agent"],"props":{"agent_id":"congyin"}}
{"id":"conv:ch9998","labels":["Conversation"],"props":{"conv_id":"ch9998"}}
{"id":"scene:chill_ai_chat","labels":["Scene"],"props":{"scene_id":"chill_ai_chat"}}
{"id":"char:congyin","labels":["Character"],"props":{"character_id":"congyin"}}
```

### 7.2 edges.jsonl 示例行

```json
{"id":"edge:OWNS_MEMORY:user:chill_ai_chat:congyin:mem:d82ae1eafae11287f949b39cb11dd939","type":"OWNS_MEMORY","src":"user:chill_ai_chat:congyin","dst":"mem:d82ae1eafae11287f949b39cb11dd939","props":{"processed_key":"d82ae1eafae11287f949b39cb11dd939","source_point_id":"074bbc5d-2eb3-4859-80db-c4f898e8820c","exported_at":"2026-02-18T03:12:42Z","created_at":"2026-02-17T19:12:27.733459-08:00"}}
{"id":"edge:TARGETS_AGENT:mem:d82ae1eafae11287f949b39cb11dd939:agent:congyin","type":"TARGETS_AGENT","src":"mem:d82ae1eafae11287f949b39cb11dd939","dst":"agent:congyin","props":{}}
{"id":"edge:FROM_CONV:mem:d82ae1eafae11287f949b39cb11dd939:conv:ch9998","type":"FROM_CONV","src":"mem:d82ae1eafae11287f949b39cb11dd939","dst":"conv:ch9998","props":{}}
{"id":"edge:IN_SCENE:mem:d82ae1eafae11287f949b39cb11dd939:scene:chill_ai_chat","type":"IN_SCENE","src":"mem:d82ae1eafae11287f949b39cb11dd939","dst":"scene:chill_ai_chat","props":{}}
{"id":"edge:HAS_CHARACTER:mem:d82ae1eafae11287f949b39cb11dd939:char:congyin","type":"HAS_CHARACTER","src":"mem:d82ae1eafae11287f949b39cb11dd939","dst":"char:congyin","props":{}}
{"id":"edge:CONV_IN_SCENE:conv:ch9998:scene:chill_ai_chat","type":"CONV_IN_SCENE","src":"conv:ch9998","dst":"scene:chill_ai_chat","props":{}}
{"id":"edge:CONV_HAS_CHARACTER:conv:ch9998:char:congyin","type":"CONV_HAS_CHARACTER","src":"conv:ch9998","dst":"char:congyin","props":{}}
{"id":"edge:USER_IN_SCENE:user:chill_ai_chat:congyin:scene:chill_ai_chat","type":"USER_IN_SCENE","src":"user:chill_ai_chat:congyin","dst":"scene:chill_ai_chat","props":{}}
{"id":"edge:AGENT_IS_CHARACTER:agent:congyin:char:congyin","type":"AGENT_IS_CHARACTER","src":"agent:congyin","dst":"char:congyin","props":{}}
```

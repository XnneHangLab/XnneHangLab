# graphify_export 规范草案

## 1. 背景与定位

当前 mem0 快照导出由 `memory_bench/scripts/replay_mem0.py export` 生成，输出为 JSONL。建议新增一个后处理脚本 `graphify_export`，消费该 JSONL 并产出图谱友好的节点/边结构，保持与 `memory_bench/scripts` 现有命名与参数风格一致。

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

- 必须是合法 JSONL；空行报错（与现有脚本严格校验风格一致）
- 顶层对象缺 `id`/`collection`/`isolation`/`exported_at` 时记 warning 并可选择跳过
- `payload` 为 `null` 时可跳过并统计 `skipped_null_payload`

## 3. 输出契约（Output Contract）

建议输出目录：`memory_bench/logs/replay_mem0/graphify/`

建议输出 3 类文件：

1. `graph_nodes_YYYYMMDD_HHMMSS.jsonl`
2. `graph_edges_YYYYMMDD_HHMMSS.jsonl`
3. `graphify_report_YYYYMMDD_HHMMSS.json`

### 3.1 nodes JSONL（建议）

每行一个 node：

- `node_id` (string)
- `node_type` (enum: `memory` | `user` | `agent` | `scene` | `conversation` | `character`)
- `label` (string)
- `source_point_id` (string | number, optional)
- `attrs` (object, optional)

### 3.2 edges JSONL（建议）

每行一个 edge：

- `edge_id` (string)
- `src` (string)
- `dst` (string)
- `edge_type` (enum: `belongs_to` | `mentioned_in` | `authored_by` | `targets_agent` | `same_hash_as`)
- `weight` (number, optional)
- `attrs` (object, optional)

### 3.3 report JSON（建议）

- `input_path`
- `nodes_path`
- `edges_path`
- `records_total`
- `records_skipped`
- `nodes_total`
- `edges_total`
- `duration_ms`
- `warnings` (array[string])

## 4. CLI 草案

脚本建议：`memory_bench/scripts/graphify_export.py`

```bash
uv run python memory_bench/scripts/graphify_export.py \
  --input memory_bench/logs/replay_mem0/export_20260218_031242.jsonl \
  --out-dir memory_bench/logs/replay_mem0/graphify \
  --format jsonl \
  --strict
```

### 参数建议

- `--input` (str, required)：export JSONL 输入
- `--out-dir` (str, default=`memory_bench/logs/replay_mem0/graphify`)
- `--prefix` (str, default=`graph`)
- `--format` (choices=`jsonl`, `jsonl+csv`)
- `--strict` (flag)：严格模式，遇到 schema 问题直接失败
- `--dedup-by-hash` (flag)：按 payload.hash 去重 memory 节点
- `--min-text-len` (int, default=1)：过滤过短 `payload.data`

### 返回码建议

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
2. 将每条 payload 映射为 `memory` 节点
3. 依据 `user_id`/`agent_id` 建 `authored_by` / `targets_agent` 边
4. 输出 nodes/edges/report 三文件
5. 使用 `bench_logger` 的 `logger.bind(group="memory")` 输出进度与统计


# claimify_all.py

## 作用

读取 mem0 export JSONL，按 conv_id 分组、按 chunk 调 LLM 抽取 claim/entity JSONL。

## 调用示例

```bash
uv run memory_bench/scripts/claimify_all.py \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl
uv run memory_bench/scripts/claimify_all.py \
  --input memory_bench/logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl \
  --workers 2 --force
```

## 参数

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

## 输出

- **正式产物**：`memory_bench/data/claims/by_conv/{conv_id}.jsonl`
- **Tag registry**：`memory_bench/resources/tag_registry.json`（增量更新）

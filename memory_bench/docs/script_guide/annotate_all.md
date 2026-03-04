# annotate_all.py

## 作用

批量调用 LLM 将章节文本标注为严格 JSONL event 流。

## 调用示例

```bash
uv run memory_bench/scripts/annotate_all.py --workers 6
uv run memory_bench/scripts/annotate_all.py --only ch05,ch06
uv run memory_bench/scripts/annotate_all.py --only ch01 --workers 1 --force
```

## 参数

| 参数 | 说明 |
|------|------|
| `--workers` | 并发章节数 |
| `--force` | 覆盖重跑 |
| `--only` | 仅处理指定 conv_id（逗号分隔） |
| `--scene-id` | scene_id |
| `--character-id` | character_id |
| `--model` | LLM model |
| `--source` | 章节来源：`auto` / `raw` / `norm` |

## 环境变量（`memory_bench/.env.benchmark`）

- `BENCHMARK_LLM_API_KEY`（必须）
- `BENCHMARK_LLM_MODEL`（可选）
- `BENCHMARK_LLM_BASE_URL`（可选）
- `BENCHMARK_LLM_RATE_LIMIT`（可选，每分钟最大 LLM 调用次数，0 = 不限制）

**优先级**：CLI > `BENCHMARK_` 环境变量 > 脚本默认值。

## 输出

- **正式产物**：`memory_bench/data/events/by_chapter/{conv_id}.jsonl`
- **调试日志**：`logs/annotate_prompt/`、`logs/annotate_raw/`、`logs/annotate_meta/`

## 返回码

- `0`：全部 ok 或 skipped
- `1`：任意章节 failed

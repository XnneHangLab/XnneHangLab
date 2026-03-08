# compile_events.py

## 作用

按 `index.json` 的章节顺序拼接 by_chapter JSONL，做严格校验后输出。

## 调用示例

```bash
uv run memory_bench/scripts/compile_events.py
uv run memory_bench/scripts/compile_events.py --chapters ch01,ch02
```

## 参数

| 参数 | 说明 |
|------|------|
| `--chapters` | 仅拼接指定章节（逗号分隔，按 index 顺序过滤） |
| `--out` | 输出 JSONL 路径 |
| `--mode` | 输出模式（默认 `preserve`） |

## 输入 / 输出

- **输入**：`memory_bench/data/events/by_chapter/{conv_id}.jsonl`
- **输出**：`memory_bench/data/events/compiled/all.jsonl`（默认）

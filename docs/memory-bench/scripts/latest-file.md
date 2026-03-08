# latest_file.py

## 作用

按 glob 模式获取目标目录下最新文件路径（stdout 输出，适合在 justfile 中用变量捕获）。

## 调用示例

```bash
uv run memory_bench/scripts/latest_file.py \
  --export-dir memory_bench/logs/replay_mem0 \
  --glob "export_*.jsonl"

uv run memory_bench/scripts/latest_file.py \
  --export-dir memory_bench/logs/claims/graphify \
  --glob "claims_nodes_*.jsonl"
```

## 参数

| 参数 | 说明 |
|------|------|
| `--export-dir` | 目标目录 |
| `--glob` | glob 模式 |

# mem0_to_graph.py

## 作用

消费 mem0 export JSONL，输出图谱 nodes/edges JSONL（增量幂等，通过 state.sqlite 管理）。

## 子命令

| 子命令 | 说明 |
|--------|------|
| `reset` | 重建 state.sqlite，可选清理输出 |
| `add` | 增量写 nodes/edges |
| `dry-run` | 只解析统计，不写产物 |

## 调用示例

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

## 参数

| 参数 | 说明 |
|------|------|
| `--input` | mem0 export JSONL 路径 |
| `--out-dir` | 输出目录 |
| `--state-db` | SQLite 状态数据库路径 |
| `--prefix` | 输出文件名前缀（默认 `graph`） |

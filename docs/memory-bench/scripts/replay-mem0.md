# replay_mem0

`memory_bench/scripts/replay_mem0.py` 用于把 benchmark 事件回放到 mem0，并支持导出快照。

## 用法

```bash
uv run memory_bench/scripts/replay_mem0.py ingest
uv run memory_bench/scripts/replay_mem0.py probe --k 10
uv run memory_bench/scripts/replay_mem0.py export
```

## 必要环境变量

- `BENCHMARK_LLM_API_KEY`
- `BENCHMARK_LLM_BASE_URL`
- `BENCHMARK_LLM_MODEL`

## 本地 Embedding

Embedding 默认走本地 OpenAI 兼容端点：

- `LOCAL_EMBEDDING_BASE_URL`，默认 `http://localhost:12395/v1`
- `LOCAL_EMBEDDING_MODEL`，默认 `bge-m3`

不再需要 `BENCHMARK_EMBEDDING_API_KEY` / `BENCHMARK_EMBEDDING_BASE_URL` / `BENCHMARK_EMBEDDING_MODEL`。

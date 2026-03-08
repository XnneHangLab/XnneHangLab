# replay_mem0.py

## 作用

将 benchmark 事件 JSONL 回放拆为 3 个子命令：

- `ingest` — 将事件流写入 Mem0（支持 checkpoint 断点续跑）
- `probe` — 对 probe 事件做 Mem0 检索并输出日志
- `export` — 导出当前 Mem0 全量快照

## 调用示例

```bash
uv run memory_bench/scripts/replay_mem0.py ingest
uv run memory_bench/scripts/replay_mem0.py ingest --isolation per_chapter
uv run memory_bench/scripts/replay_mem0.py probe --k 10
uv run memory_bench/scripts/replay_mem0.py export
uv run memory_bench/scripts/replay_mem0.py export --infer-owner --owner-fallback Agent
```

## 必需环境变量

需要同时配置 LLM 和 Embedding（共 6 项）：

- `BENCHMARK_LLM_API_KEY` / `BENCHMARK_LLM_BASE_URL` / `BENCHMARK_LLM_MODEL`
- `BENCHMARK_EMBEDDING_API_KEY` / `BENCHMARK_EMBEDDING_BASE_URL` / `BENCHMARK_EMBEDDING_MODEL`

## 子命令

| 子命令 | 说明 |
|--------|------|
| `ingest` | 回放写入 Mem0，支持 checkpoint 断点续跑 |
| `probe` | 对 probe 事件做检索测试 |
| `export` | 导出 Mem0 全量快照为 JSONL |

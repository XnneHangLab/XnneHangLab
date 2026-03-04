# compiled_claims.py

## 作用

将 `claimify_all.py` 产出的 by_conv JSONL 全量汇总去重。

## 调用示例

```bash
uv run memory_bench/scripts/compiled_claims.py --force
```

## 参数

| 参数 | 说明 |
|------|------|
| `--in-dir` | 输入目录（默认 by_conv） |
| `--out-dir` | 输出目录 |
| `--force` | 允许覆盖 |

## 输出

- `memory_bench/data/claims/compiled/entities.jsonl`
- `memory_bench/data/claims/compiled/claims.jsonl`
- `memory_bench/data/claims/compiled/compiled_meta.json`

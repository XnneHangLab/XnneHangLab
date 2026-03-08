# build_index.py

## 作用

扫描 `memory_bench/data/source/raw/` 章节文件，关联 `norm/`，生成 `memory_bench/data/source/index.json`。

## 调用示例

```bash
uv run memory_bench/scripts/build_index.py
uv run memory_bench/scripts/build_index.py --force
uv run memory_bench/scripts/build_index.py --limit 5          # 仅前 5 章
uv run memory_bench/scripts/build_index.py --tail 3           # 仅最后 3 章
uv run memory_bench/scripts/build_index.py --offset 2 --limit 3  # 跳过前 2 章取 3 章
```

## 参数

| 参数 | 说明 |
|------|------|
| `--force` | 即使 index 已存在也强制重建 |
| `--limit N` | 仅索引前 N 章（按章节号排序） |
| `--tail N` | 仅索引后 N 章 |
| `--offset N` | 跳过前 N 章后再 limit/tail |

## 输入 / 输出

- **输入**：`memory_bench/data/source/raw/*.md` + `norm/*.norm.md`（可选）
- **输出**：`memory_bench/data/source/index.json`

# claims_to_graph.py

## 作用

将 compiled claims/entities JSONL 转换为图谱 nodes/edges JSONL。

## 子命令

| 子命令 | 说明 |
|--------|------|
| `add` | 导出 nodes/edges |
| `dry-run` | 只解析统计 |

## 调用示例

```bash
uv run memory_bench/scripts/claims_to_graph.py add
uv run memory_bench/scripts/claims_to_graph.py dry-run
```

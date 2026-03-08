# claim_extractor.py

## 作用

实时 claim/entity 提取模块，是 `claimify_all.py` 的实时对应物。

接收 `mem0.add()` 返回的轻量 results，通过 LLM 提取 claim/entity 记录，供 `graph_writer.py` 写入 Neo4j。

## 核心函数

| 函数 | 说明 |
|------|------|
| `prepare_memory_items()` | 过滤 mem0 results，生成 prompt-ready items |
| `build_prompt()` | 构建简化版 claim extraction prompt |
| `parse_llm_output()` | 解析 LLM 返回的 JSONL，逐行校验 |
| `extract_claims()` | 主入口：prepare → prompt → LLM call → parse |

## 设计决策

- **简化 prompt**：不需要 `point_id`/`hash`/`conv_id` 等离线字段
- **优雅降级**：LLM 返回空/格式错误 → 记日志 + 返回 `[]`
- **无 tag registry**：实时模式跳过跨对话去重
- **严格验证**：confidence < 0.6 的 claim 不输出

## 与离线管线的关系

```
离线管线（batch）：
  replay_mem0 export → claimify_all.py → ...

实时管线（realtime）：
  mem0.add() results → claim_extractor.py → graph_writer.py → Neo4j
```

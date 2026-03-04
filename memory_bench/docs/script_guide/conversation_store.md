# conversation_store.py

## 作用

日期为基础的对话 JSONL 持久化存储模块，为 `chat_router.py` 提供轻量级对话历史管理。

## 文件结构

```
conversations/
├─ 2026-03-03.json
├─ 2026-03-04.json
└─ 2026-03-05.json
```

每个文件包含一个消息列表（JSON 格式）。

## 核心函数

| 函数 | 说明 |
|------|------|
| `read_conversation(date_id)` | 读取指定日期的对话消息 |
| `append_turn(date_id, role, content, extra)` | 追加一条新消息 |
| `list_conversations()` | 列出所有可用的对话日期 ID |
| `get_today_id()` | 获取今天的日期 ID（`YYYY-MM-DD`） |

## 使用方式

```python
from memory_bench.server.conversation_store import ConversationStore

conv_store = ConversationStore(base_dir="conversations")
today = conv_store.get_today_id()
messages = conv_store.read_conversation(today)
conv_store.append_turn(today, role="user", content="你好")
```

## 设计决策

- **日期分文件**：便于按天归档和清理
- **无依赖**：只用标准库 `json` 和 `pathlib`
- **优雅降级**：文件不存在/损坏时返回空列表

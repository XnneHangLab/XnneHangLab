# chat_router.py

## 作用

轻量级 FastAPI router，提供 `/memory/chat` 端点，兼容 AIChat 客户端的对话协议。

与 `router.py`（OpenAI 兼容的 `/v1/chat/completions` 代理）不同，`chat_router.py` 是简化版本：
- **单一端点**：`POST /memory/chat`
- **简化请求/响应模型**：直接传 `message`，返回 `content`
- **内置对话存储**：集成 `conversation_store.py`，无需 mem0
- **可选图谱写入**：通过 `--enable-graph` 启用实时 claim 提取和 Neo4j 写入

## 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/memory/chat` | POST | 对话端点（兼容 AIChat 客户端） |
| `/memory/sessions` | GET | 列出可用的对话日期 |
| `/memory/health` | GET | 健康检查 |

## 请求/响应格式

**请求**：
```json
{
  "session_id": "sess_xxx",
  "message": "你好",
  "model": "gpt-4o-mini"
}
```

**响应**：
```json
{
  "session_id": "sess_xxx",
  "content": "你好呀！",
  "model": "gpt-4o-mini",
  "created": 1709553600
}
```

## 系统 Prompt 构建

从 `prompts/` 目录动态拼接：

```
prompts/
├─ emotion/
│  ├─ base_persona.txt      （基础人设）
│  └─ emotion_system.txt    （情绪系统）
├─ tools/
│  └─ tool_definitions.txt  （工具定义，可选）
└─ diary/
   └─ recent_summary.txt    （日记摘要，可选）
```

## 与 router.py 的对比

| 特性 | `chat_router.py` | `router.py` |
|------|-----------------|-------------|
| **端点** | `/memory/chat` | `/memory/v1/chat/completions` |
| **协议** | 简化自定义协议 | OpenAI 兼容 |
| **对话存储** | `conversation_store.py` | mem0（Qdrant） |
| **适用场景** | AIChat 客户端、轻量级对话 | 需要记忆检索的复杂场景 |

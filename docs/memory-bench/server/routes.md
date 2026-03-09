# 路由与端点

Memory Chat Server 暴露两组 API，挂载在同一个 FastAPI 应用上：

```python
app.include_router(router)                    # /v1/chat/completions, /v1/models, /health
app.include_router(chat_router, prefix="/memory")  # /memory/chat, /memory/sessions, /memory/health
```

---

## 透明代理（router.py）

### `POST /v1/chat/completions`

OpenAI 兼容的对话端点，在转发前注入记忆。

**请求格式**（标准 OpenAI）：

```json
{
  "model": "google/gemini-2.0-flash",
  "messages": [
    {"role": "system", "content": "你是一个助手"},
    {"role": "user", "content": "我上次说了什么？"}
  ],
  "temperature": 0.7,
  "max_tokens": 2000,
  "stream": false
}
```

**响应格式**（标准 OpenAI）：

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1709553600,
  "model": "google/gemini-2.0-flash",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "你上次提到了..."},
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 50,
    "total_tokens": 200
  }
}
```

**处理流程**：

```
请求进入
  ↓
1. 提取最新 user message
  ↓
2. mem0.search() → 检索相关记忆
  ↓
3. 将记忆注入 system prompt 末尾
   （## Recalled Memories 模板）
  ↓
4. 转发给 LLM Provider
  ↓
5. 返回原始响应
  ↓
6. 异步后台：mem0.add() 写回记忆
   → claim_extractor → graph_writer → Neo4j
```

> [!NOTE] 认证：通过 `--server-api-key` 或 `CHAT_SERVER_API_KEY` 环境变量启用 Bearer token 认证。未配置时无需认证。

### `GET /v1/models`

返回当前配置的模型信息，兼容 OpenAI `/v1/models` 接口。

### `GET /health`

健康检查端点。

```json
{
  "status": "ok",
  "mem0_ready": true,
  "llm_ready": true,
  "model": "google/gemini-2.0-flash",
  "graph_pipeline_enabled": true,
  "claim_llm_model": "google/gemini-2.0-flash"
}
```

---

## 自治 Agent（chat_router.py）

### `POST /memory/chat`

自治对话端点，Server 管理 session、上下文和工具调用。

**请求格式**：

```json
{
  "session_id": "sess_abc123",
  "message": "帮我写一篇日记",
  "model": "gpt-4o-mini"
}
```

| 字段 | 必填 | 说明 |
|------|:---:|------|
| `session_id` | ❌ | 不传则自动生成 `sess_<uuid>` |
| `message` | ✅ | 用户消息 |
| `model` | ❌ | 覆盖默认模型 |

**响应格式**：

```json
{
  "session_id": "sess_abc123",
  "content": "[Happy] 好的！我来帮你写今天的日记~",
  "model": "gpt-4o-mini",
  "created": 1709553600
}
```

**处理流程**：

```
请求进入
  ↓
1. 获取/创建 session_id
  ↓
2. 从 conversations/YYYY-MM-DD.json 读取对话历史
  ↓
3. 拼接 system prompt
   （persona + emotion + tools + diary）
  ↓
4. 组装 messages: [system, ...history, user]
  ↓
5. 调用 LLM（带 tools 定义）
  ↓
6. Tool-loop（如果 LLM 返回 tool_calls）:
   ├─ 执行工具 → 结果塞回 messages
   └─ 再次调用 LLM → 重复直到无 tool_calls
  ↓
7. 持久化 user + assistant 到日期 JSON
  ↓
8. 返回最终响应
```

### 🔧 内置工具

LLM 通过 function calling 调用这四个工具：

#### READ

读取文件内容或列出目录。

```json
{
  "name": "READ",
  "arguments": {
    "path": "memory_bench/server/memory/MEMORY.md"
  }
}
```

也支持通过 `purpose` 快捷访问预设位置：

| purpose | 对应路径 |
|---------|---------|
| `memory` | `memory_bench/server/memory/MEMORY.md` |
| `diary` | `memory_bench/data/diary/` |
| `saved` | `memory_bench/data/saved/` |
| `prompt` | `memory_bench/server/prompts/` |
| `conversation` | `memory_bench/conversations/` |

#### WRITE

创建或覆盖文件（限 `memory_bench/` 内部）。

```json
{
  "name": "WRITE",
  "arguments": {
    "content": "# 2026-03-04 日记\n\n今天天气不错...",
    "purpose": "diary"
  }
}
```

#### EDIT

精确替换文件中的文本（限 `memory_bench/` 内部）。

```json
{
  "name": "EDIT",
  "arguments": {
    "path": "memory_bench/server/prompts/emotion/base_persona.txt",
    "old_text": "性格有点内向",
    "new_text": "性格温柔，有点内向"
  }
}
```

#### SEARCH

在指定范围内搜索关键词。

```json
{
  "name": "SEARCH",
  "arguments": {
    "query": "聪音",
    "scope": "memory_bench",
    "file_pattern": "*.md"
  }
}
```

| scope | 搜索范围 |
|-------|---------|
| `workspace` | 整个 XnneHangLab 仓库 |
| `memory_bench` | memory_bench/ 目录 |
| `diary` | memory_bench/data/diary/ |
| `prompts` | memory_bench/server/prompts/ |
| `saved` | memory_bench/data/saved/ |

### `GET /memory/sessions`

列出所有可用的对话日期。

```json
{
  "sessions": ["2026-03-03", "2026-03-04", "2026-03-04_02"],
  "count": 3
}
```

### `GET /memory/health`

Chat 端点的健康检查。

```json
{
  "status": "ok",
  "llm_ready": true,
  "model": "gpt-4o-mini",
  "prompts_dir": "/path/to/prompts",
  "conversations_dir": "/path/to/conversations"
}
```

---

## 🚀 启动配置

### 环境变量（`.env.benchmark`）

```bash
# Chat LLM
CHAT_API_KEY=sk-xxx
CHAT_BASE_URL=https://openrouter.ai/api/v1
CHAT_MODEL=google/gemini-2.0-flash

# mem0 LLM（默认复用 Chat LLM）
MEM0_LLM_API_KEY=
MEM0_LLM_BASE_URL=
MEM0_LLM_MODEL=

# Embedding
BENCHMARK_EMBEDDING_API_KEY=sk-xxx
BENCHMARK_EMBEDDING_BASE_URL=https://api.openai.com/v1
BENCHMARK_EMBEDDING_MODEL=text-embedding-3-small

# 认证（可选）
CHAT_SERVER_API_KEY=your-secret-key

# 图谱管线（可选）
ENABLE_GRAPH=true
CLAIM_LLM_API_KEY=
CLAIM_LLM_BASE_URL=
CLAIM_LLM_MODEL=
NEO4J_CONTAINER=membench-neo4j-mem0
```

### CLI 快速启动

```bash
# 最简（依赖 .env.benchmark）
just memory-chat-server

# 指定端口
just memory-chat-server 9090

# 完整参数
uv run memory_bench/server/chat_server.py \
  --chat-api-key sk-xxx \
  --chat-base-url https://openrouter.ai/api/v1 \
  --chat-model google/gemini-2.0-flash \
  --enable-graph \
  --port 8080
```

---

## 📚 延伸阅读

- [设计理念](./design) — 架构决策与安全模型
- [chat_server.py 脚本文档](/memory-bench/scripts/chat-server) — CLI 参数详情
- [chat_router.py 脚本文档](/memory-bench/scripts/chat-router) — 实现细节
- [conversation_store.py 脚本文档](/memory-bench/scripts/conversation-store) — 持久化实现

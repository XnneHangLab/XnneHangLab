# chat_server.py

## 作用

独立启动器 + CLI，用于启动 Memory Chat Server。

## 调用示例

```bash
# 通过 justfile
just memory-chat-server          # 默认端口 8080
just memory-chat-server 9090     # 自定义端口

# 直接调用
uv run memory_bench/server/chat_server.py --port 8080

# 指定所有参数
uv run memory_bench/server/chat_server.py \
  --chat-api-key sk-xxx \
  --chat-base-url https://openrouter.ai/api/v1 \
  --chat-model google/gemini-2.0-flash \
  --embedding-api-key sk-xxx \
  --embedding-base-url https://api.openai.com/v1 \
  --embedding-model text-embedding-3-small \
  --port 8080
```

## 参数

| 参数 | 说明 |
|------|------|
| `--port` | 服务端口（默认 8080） |
| `--chat-api-key` | Chat LLM API key |
| `--chat-base-url` | Chat LLM base URL |
| `--chat-model` | Chat 模型名 |
| `--embedding-*` | Embedding 配置 |
| `--enable-graph` | 启用实时 graph pipeline |

## 功能

- CLI 参数解析
- env 加载（委托给 `startup.py`）
- uvicorn 启动

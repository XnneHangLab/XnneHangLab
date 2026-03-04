# chat_cli.py

## 作用

终端交互式对话调试客户端，通过 HTTP 调用 Memory Chat Server。

## 特性

- 自动加载 `22_PERSONA_CANON.md` 作为 system prompt（聪音人设）
- `xnne>` / `congyin>` 提示符
- 上下文 in-memory，不持久化
- 支持 `--base-url` / `--system` / `--no-persona` / `--api-key`

## 调用示例

```bash
# 前提：先启动 server
just memory-chat-server

# 另一终端启动 CLI
just memory-chat-cli
just memory-chat-cli base_url=http://localhost:9090

# 或直接调用
uv run memory_bench/server/chat_cli.py

# 跳过 persona 加载
uv run memory_bench/server/chat_cli.py --no-persona
```

## 环境变量

| 环境变量 | 说明 | 回退 |
|----------|------|------|
| `CHAT_CLI_BASE_URL` | Server base URL | `http://localhost:8080` |
| `CHAT_SERVER_API_KEY` | Server 鉴权密钥 | 不设则不鉴权 |

## 退出方式

- 输入 `quit` 或 `exit`
- Ctrl+C / Ctrl+D

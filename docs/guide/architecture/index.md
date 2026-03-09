# 架构概览

本文描述 XnneHangLab 主项目（`src/lab/`）的整体分层与模块职责，帮助开发者快速定位代码。

## 分层结构

```
src/lab/
├── 入口层
│   ├── server.py                 # FastAPI 服务（主入口，WebSocket + HTTP API）
│   └── streamlit/app.py              # Streamlit WebUI 入口（页面路由）
│
├── 通信层
│   ├── websocket_handler.py      # WebSocket 协议处理
│   └── message_handler.py        # 消息事件总线
│
├── 对话层
│   ├── conversations/            # 对话编排、TTS 管理、中断处理
│   └── service_context.py        # 会话上下文（Agent + 配置）
│
├── 智能体层
│   ├── agent/                    # Agent 框架（LLM 调用、记忆管理）
│   └── mcp/                      # 工具调用（MCP 协议）
│
└── 基础设施层
    ├── api/                      # HTTP 路由 & TTS/ASR 客户端
    ├── asr/                      # 语音识别（FunASR / Whisper）
    ├── config_manager/           # 配置管理（TOML 加载）
    ├── logger/                   # 分组日志
    ├── streamlit/                # Streamlit UI 页面与样式
    │   ├── app.py                # 页面路由入口（原 ui.py）
    │   ├── style.py              # 全局 CSS 样式注入
    │   ├── i18n.py               # UI i18n 枚举（Device / Guide / SubtitleSpeed 等）
    │   ├── session_keys.py       # session_state key 常量
    │   ├── project/              # 主功能页（主页、音频识别）
    │   ├── setting/              # 设置页
    │   └── dialogs/              # 对话框组件
    ├── utils/                    # 工具函数（音频处理、文本工具）
    └── cli.py                    # CLI 工具（ASR 命令行）
```

**外部客户端：**
- [Open-LLM-VTuber-Web](https://github.com/XnneHangLab/Open-LLM-VTuber-Web) — VTuber 前端（WebSocket 连接）
- [AIChat](https://github.com/XnneHangLab/AIChat) — 对话客户端（WebSocket 连接）

## 请求流程

一个典型的语音对话请求经过以下路径：

1. **客户端连接** → `server.py` 建立 WebSocket 连接
2. **消息路由** → `websocket_handler.py` 解析协议，分发到对应处理器
3. **对话触发** → `conversations/` 判断对话类型（语音输入 / 文字输入 / 群聊），创建对话任务
4. **上下文准备** → `service_context.py` 组装 Agent、加载 Prompt 和 Live2D 模型配置
5. **Agent 推理** → `agent/` 调用 LLM，可能触发 MCP 工具循环
6. **响应生成** → Agent 返回文本，经断句后发送给 TTS
7. **音频合成** → `api/` 调用 GPT-SoVITS / Qwen-TTS 生成音频
8. **回传客户端** → 音频 + 字幕 + Live2D 表情通过 WebSocket 推送

## 模块速查

| 模块 | 路径 | 职责 | 详情 |
|------|------|------|------|
| **Agent** | `agent/` | LLM 调用、工具循环、记忆存储 | [→ agent](./agent) |
| **API** | `api/` | HTTP 路由、TTS/ASR 客户端封装 | [→ api](./api) |
| **ASR** | `asr/` | FunASR / Whisper 语音识别 | [→ asr](./asr) |
| **MCP** | `mcp/` | MCP 工具服务器、工具注册与路由 | [→ mcp](./mcp) |
| **Conversations** | `conversations/` | 对话编排、TTS 管理、中断处理 | [→ conversations](./conversations) |
| **Config** | `config_manager/` | TOML 配置加载与校验 | [→ config](./config) |
| **Live2D** | `live2d_model.py` | Live2D 模型 Payload 构建 | — |
| **Logger** | `logger/` | 分组日志 | — |
| **Streamlit** | `streamlit/` | Streamlit UI 页面与全局样式 | — |
| **Utils** | `utils/` | 音频处理、文本工具、控制台 | — |

## 关键设计决策

### 单一 LLM Provider

项目只保留 OpenAI Compatible 接口。`LLMFactory` 直接返回 `AsyncLLM`，不做 provider 分支。所有后端（DeepSeek、Qwen 等）通过 `base_url` 切换。

### Agent = MemoryAgent

当前只有一个 Agent 实现：`MemoryAgent`。它同时负责对话、工具调用和记忆存储。`AgentFactory` 存在是为未来多 Agent 预留。

### MCP 工具框架

工具通过 [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) 接入，支持远程工具服务器。`FastMcpRouter` 管理多 server 连接，`ToolRegistry` 处理工具解析和执行。

### 对话中断

支持两种中断模式：个体中断（用户打断 AI 说话）和群聊中断。中断信号通过 `MessageHandler` 事件总线传递。

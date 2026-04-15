# 架构概览

本文描述 XnneHangLab 主项目 `src/lab/` 的整体分层与模块职责，方便快速定位代码。

---

## 分层结构

```text
src/lab/
├── 入口层
│   └── server.py                 # FastAPI 服务入口
├── 通信层
│   ├── websocket_handler.py      # WebSocket 协议处理
│   └── message_handler.py        # 消息事件总线
├── 对话层
│   ├── conversations/            # 对话编排、TTS 管理、中断处理
│   └── service_context.py        # 会话上下文组装
├── 智能体层
│   └── agent/                    # Agent 框架、工具调度、记忆调用
└── 基础设施层
    ├── api/                      # HTTP 路由与客户端
    ├── asr/                      # FunASR / Whisper
    ├── config_manager/           # TOML 配置加载与校验
    ├── logger/                   # 分组日志
    ├── utils/                    # 文本/音频工具函数
    └── cli/                      # CLI 工具
```

---

## 请求流程

一个典型的语音对话请求大致会经过这些阶段：

1. 客户端通过 `server.py` 建立 WebSocket 连接
2. `websocket_handler.py` 解析协议并分发消息
3. `conversations/` 创建和管理会话任务
4. `service_context.py` 组装配置、Agent 与上下文
5. `agent/` 调用 LLM，并按需使用工具、技能和记忆 hook
6. Agent 返回文本，再进入 TTS 与字幕链路
7. 最终结果通过 WebSocket 回传给客户端

---

## 模块速查

| 模块 | 路径 | 职责 | 详情 |
|---|---|---|---|
| Agent | `agent/` | LLM 调用、工具调度、记忆与生命周期 | [→ agent](./agent) |
| API | `api/` | HTTP 路由、TTS/ASR 客户端封装 | [→ api](./api) |
| ASR | `asr/` | FunASR / Whisper 语音识别 | [→ asr](./asr) |
| Conversations | `conversations/` | 对话编排、TTS 管理、中断处理 | [→ conversations](./conversations) |
| Config | `config_manager/` | TOML 配置加载与校验 | [→ config](./config) |
| Tools | `tools/` / `plugins/` | BuiltinTool、工具插件与 ToolManager | [→ tools](./tools) |
| Plugin System | `plugin/` / `plugins/` | 插件发现、加载与类型分发 | [→ plugin-system](./plugin-system) |
| Profile System | `profile/` | persona、format、skill 注入 | [→ profile-system](./profile-system) |
| Skills | `plugins/` / `profile/` | SkillDescriptor 与 system prompt 注入 | [→ skills](./skills) |
| Memory Agent | `agent/agents/memory_agent/` | 当前主 Agent 实现 | [→ memory-agent](./memory-agent) |

---

## 关键设计决策

### 单一 LLM Provider 接口

项目保留统一的 OpenAI-compatible 调用方式，不把上层逻辑绑死在某一家 provider 上。这样模型源可以换，调用方式尽量别换。

### Agent = MemoryAgent

当前主实现仍然是 `MemoryAgent`。`AgentFactory` 保留了工厂层，是为了让未来扩展更多 Agent 时不需要回头拆主流程。

### 内置工具 + 插件工具

高频基础能力直接做成 `BuiltinTool`，比如读写文件、列目录、获取时间；联网搜索、网页抓取、截图这类能力则通过插件系统挂到 `ToolManager`。这样既轻，又保留可扩展性。

### Skill 注入而不是硬编码流程

Skill 不直接执行动作，而是通过 `SystemPromptBuilder` 注入操作指引。这样“怎么做事”的知识可以放进插件，而不是散落在代码分支里。

### 对话中断

系统支持中断控制，相关信号通过 `MessageHandler` 和会话层传递，让 TTS、字幕和对话状态能同步停下来。

# AgentCore 架构

> 🚧 文档施工中，待 `feat/agent-core` PR 合入后补全。

## 概览

`AgentCore` 是 `MemoryAgent`（VTuber）和 `/memory/chat`（HTTP endpoint）的共享核心，统一了以下逻辑：

- Tool loop（`AgentToolLoop`，`tool_llm` 驱动）
- Vision summary（`VisionSummarizer`，`vision_llm` 驱动）
- Prompt 拼装（`PromptBuilder`）
- Memory context 注入（`ContextInjector`）
- 流式对话（`chat_llm`）

两端的差异只在**输出处理**和**历史存储**，通过 `ConversationStorage` Protocol 插拔。

## ConversationStorage

```
ConversationStorage (Protocol)
├── MemoryStoreAdapter    ← VTuber / MemoryAgent 使用
└── ConversationStoreAdapter  ← /memory/chat 使用
```

## 数据流

```
待补全（feat/agent-core 合入后）
```

## 调用方

| 调用方 | Storage | 输出方式 |
|---|---|---|
| `MemoryAgent` | `MemoryStoreAdapter` | 流式 TTS + Live2D |
| `/memory/chat` | `ConversationStoreAdapter` | 攒完 → JSON |

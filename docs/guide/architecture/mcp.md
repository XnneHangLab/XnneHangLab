# MCP 模块

`src/lab/mcp/` — 消息类型定义与工具调用基础设施。

::: info MCP 依赖已移除
`FastMcpRouter`、`ToolRegistry`、`context_policy`、`state_updater` 等 MCP 上层逻辑已在 PR #298（clean-mcp）中删除。
`src/lab/mcp/` 现在仅保留通用类型定义和工具函数，与 MCP 协议本身不再直接关联。
工具管理由 `src/lab/tools/` 接管，详见 [工具系统](./plugin-system.md)。
:::

## 目录结构

```
mcp/
├── __init__.py    # 导出核心类型
├── _typing.py     # OpenAIMessage / ContentPart / ConversationState 等类型定义
└── util.py        # JSON 规范化、重试工具函数
```

## 核心类型（`_typing.py`）

这些类型被 `agent/`、`tools/` 等模块广泛使用：

| 类型 | 说明 |
|------|------|
| `OpenAIMessage` | OpenAI messages 格式（role / content / tool_call_id / name） |
| `TextPart` / `ImagePart` / `AudioPart` / `FilePart` | 多模态 content 类型 |
| `ContentPart` | 上述类型的 Union |
| `ConversationState` | 对话状态容器（messages / refs / slots / active_task） |
| `ToolCallLike` | OpenAI tool_call Protocol（id / function.name / function.arguments） |
| `ToolTraceItem` | 工具调用 trace（server / name / args / raw_result / ok / error） |
| `ScreenShotResult` / `ImageRefResult` | 截图工具返回类型 |

## 工具函数（`util.py`）

| 函数 | 说明 |
|------|------|
| `call_with_short_retry` | 带短暂重试的异步调用包装（用于 LLM API 调用） |
| `dump_openai_msg` | 将 `OpenAIMessage` 序列化为可读字符串（调试用） |
| `prompt_result_to_text` | 将工具调用结果转为文本 |
| `normalize_jsonlike` | 将类 JSON 对象规范化为标准 dict |

## 与其他模块的关系

```
mcp._typing  ←  core.py / storage.py / message_factory.py
             ←  memory_store.py / vision_summarizer.py
             ←  stateless_llm/openai_compatible_llm.py
             ←  tools/manager.py / tools/base.py

mcp.util     ←  stateless_llm/openai_compatible_llm.py（call_with_short_retry）
```

工具的注册、调度、执行由 `src/lab/tools/` 负责，见下节。

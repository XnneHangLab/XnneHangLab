# MCP 模块

`src/lab/mcp/` — MCP (Model Context Protocol) 工具框架。

## 目录结构

```
mcp/
├── __init__.py           # 导出核心类型和工具
├── fastmcp_router.py     # FastMcpRouter：多 MCP server 路由
├── tool_registry.py      # ToolRegistry：工具解析、执行、trace 收集
├── context_policy.py     # 上下文策略：判断是否需要历史消息
├── state_updater.py      # ConversationState 更新器
├── util.py               # JSON 规范化工具
├── _typing.py            # MCP 相关类型定义
├── server/               # 内置 MCP 服务器
│   ├── tool_server.py    # 工具服务器（文件读写、搜索、截图等）
│   ├── vision_server.py  # 视觉服务器（图片分析）
│   └── timeemi_server.py # 时间服务器（日期时间、骰子）
└── example/              # 示例配置
```

## 核心概念

### MCP (Model Context Protocol)

[MCP](https://modelcontextprotocol.io/) 是一个标准化的工具调用协议，允许 LLM 通过统一接口调用外部工具。XnneHangLab 支持：

- **内置工具服务器**（`server/`）— 文件操作、网页搜索、截图、时间查询
- **远程工具服务器**（HTTP/SSE）— 通过 `FastMcpRouter` 连接

### FastMcpRouter

多 MCP server 路由器，负责：
- 连接多个 MCP server（HTTP/Streamable HTTP）
- 生成 OpenAI tools schema（`list_tools_openai_schema()`）
- 按 namespace 路由工具调用（`call_tool()`）

工具名格式：`{namespace}__{tool_name}`（默认分隔符 `__`）

### ToolRegistry

工具注册表，提供：
- `parse_tool_calls()` — 从 LLM 响应中提取 tool_call
- `execute_tool()` — 执行单个工具，返回 `ToolTraceItem`
- `collect_trace()` — 收集完整 trace（包含图片引用）

### Context Policy

判断工具调用是否需要历史消息上下文。规则：
- 包含上下文线索（"继续"、"刚才"、"那个"）→ 需要
- 包含选择线索（"第 2 个"、"A"）→ 需要
- 包含确认线索（"对"、"可以"）→ 需要
- 包含代词开头（"它"、"这"）→ 需要
- 包含 URL / 文件路径 → 不需要（显式输入）

### ConversationState

工具循环的状态容器，包含：
- `messages` — 对话历史
- `tool_trace` — 工具调用 trace
- `tool_outputs` — 工具输出缓存
- `context_config` — 上下文策略配置

## 工具调用流程

```
LLM 返回 tool_calls
    ↓
ToolRegistry.parse_tool_calls()
    ↓
[需要上下文?] → ContextPolicy.should_include_context()
    ↓
ToolRegistry.execute_tool() → FastMcpRouter.call_tool()
    ↓
收集 ToolTraceItem（包含图片引用）
    ↓
拼接 tool message 返回 LLM
```

## 与其他模块的关系

- **agent/mcp_tool_loop.py** 使用 `ToolRegistry` 执行工具循环
- **agent/agents/memory_agent/tool_runner.py** 封装工具执行逻辑
- **service_context.py** 初始化 `FastMcpRouter` 并连接 MCP servers

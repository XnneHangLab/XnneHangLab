# MCP 模块

::: warning 已完全移除
`src/lab/mcp/` 整个包已在 PR #299（transfer-mcp-types）中删除。

- 类型定义（`OpenAIMessage`、`ContentPart`、`ConversationState` 等）已迁移到 `src/lab/agent/types.py`
- 工具函数（`call_with_short_retry`、`dump_openai_msg` 等）已迁移到 `src/lab/agent/types.py`
- MCP 上层逻辑（`FastMcpRouter`、`ToolRegistry`、`context_policy`、`state_updater`）已在 PR #298（clean-mcp）中删除
- 工具管理由 `src/lab/tools/` 接管

本页保留为历史参考，实际代码请查看 [Agent 类型系统](./agent.md) 和 [工具系统](./plugin-system.md)。
:::

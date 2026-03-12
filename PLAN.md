# PLAN.md

## 已完成

### feat/memory-bench-chat-llm-integration (#269 已合入)

memory_bench proxy_router 内嵌到 src/lab，统一配置入口。

### Bug Fix：memory_bench LLM 配置回环问题（已修复）

在 `[memory_bench]` 块加了 `upstream_llm_provider` 字段，分离了 proxy 转发目标和 chat_model provider。

### chat_router 迁移到 src/lab（本次 PR）

**变更：**
- `memory_bench/server/chat_router.py` → `src/lab/api/routes/chat.py`  
- `memory_bench/server/conversation_store.py` → `src/lab/conversation/store.py`
- 删除 `memory_bench/server/tools/`（file_tools.py、search_tools.py），已被 `src/lab/tools/builtin` 替代
- chat endpoint 现在使用 `ToolManager` + `AsyncLLM`，直接 import memory_bench 的 `search_memories()` / `memory_and_graph_background()`
- 聊天终端 现在使用 `ToolManager` + `AsyncLLM`，直接导入 memory_bench 的 `search_memories()` / `memory_and_graph_background()`  
- memory_bench 职责纯化：只做记忆存取 + 图谱管线

**架构对齐 #262：**
- memory_bench = 脑子（纯记忆后端）
- src/lab = 身体（Agent 编排、tool loop、prompt 拼装、/chat 端点）

### #279 ToolRegistry 去中心化 + MCP 配置清理（#282 已合入 dev）

**已完成（#282）：**
- 删除 timeemi / vision / tool 三个 MCP server 文件
- 清理 `config_manager/mcp.py` 里已迁移工具的配置类
- `memory_agent/agent.py` 删除三个 server 的自动连接逻辑

**#280 已关闭**（ToolPlugin 实现目录结构与 #281 理念冲突，重来）

---

## 待做

### PR A：ToolRegistry 去中心化 + 清理（#283，已完成待合入）

- [x] `src/lab/tools/plugin.py` — ToolPlugin 抽象基类 + PromptSegment
- [x] `src/lab/mcp/tool_registry.py` — 删除 if/elif 手写分支，变成轻量注册表，删除 RollDice 全部残留
- [x] `src/lab/mcp/_typing.py` — 删除已无用类：RollDice*/ScreenShot*/WebSearch*/WebFetch*/GetDateAndTime*
- [x] `src/lab/agent/mcp_tool_loop.py` — 修复 L431 cache sig bug
- [x] `src/lab/mcp/example/openai_client.py` — 删除（已被 MemoryAgent 完全取代）

### PR B：#281 Plugin 生态 — plugin.toml + PluginLoader（接 PR A）

> 详见 #281，每个 plugin 独立目录，自带 plugin.toml，配置不进 src/lab

- [ ] `plugins/` 根目录结构建立
- [ ] `plugin.toml` Pydantic schema（`src/lab/plugin/schema.py`）
- [ ] `PluginLoader`（从目录加载 + 读 plugin.toml + 合并 profile 配置）
- [ ] web_fetch / web_search_ddg / web_search_searxng / screen_shot 实现搬进各自 `plugins/<id>/` 目录
- [ ] 清理 `config_manager/mcp.py` 残留的 web_search/web_fetch 配置项

### PR C：#278 Profile 配置驱动 System Prompt 拼接（接 PR B）

> 详见 #278，Profile toml → PluginLoader + SystemPromptBuilder

- [ ] `Profile` Pydantic model + ProfileLoader
- [ ] `SystemPromptBuilder` 正式实现（替换 chat.py 里的 `_build_system_prompt()`）
- [ ] `server.py` 改为从 Profile 驱动，删除硬编码路径
- [ ] 启动参数 / 环境变量支持指定 profile 文件

### AgentLoop 重构 — 废弃 mcp_tool_loop.py（接 PR B/C）

> `mcp_tool_loop.py` 命名撒谎（含 builtin 逻辑）、职责混乱（loop 核心 + 截图指代消解 + web_search 串行策略 + 后处理 if/else 全塞一起）、硬编码中文关键词。待 PluginLoader 合入后重构。关联 #262 Phase 4/5

- [ ] 新建 `AgentLoop`：纯循环逻辑（while tool_call → ToolManager.call → 回填 → 下一轮），不含任何业务 if/else
- [ ] 截图复用逻辑下沉：`_user_wants_reuse_screenshot` / `_can_reuse_last_image` 等移入 `ScreenShotPlugin` 自身的 hook / state
- [ ] web_search 串行策略下沉：移入 ToolPlugin 配置项或 HookPlugin
- [ ] 废弃 `mcp_tool_loop.py`

### 后续清理（可选）

- [ ] 评估 `memory_bench/server/chat_server.py` standalone 启动器是否还需要（已移除 chat_router mount，但文件保留）

---

## 后续 PR 计划（来自 feat/agent-core 讨论）

### PR：流式并行 Tool Call（合并 Tool Model + Chat Model）

> 当前双模型串行架构的缺陷：tool call 只能在回复前，无法在回复中途触发；chat model 不感知自己的工具能力。
>
> 新架构：Chat Model 同时传 `tools=schema` 和 `stream=True`，流式输出的同时监听 tool_call chunk，异步派发执行，结果追加上下文后继续流式生成。

- [ ] `AgentCore.run_turn()` 改为单模型流式 + tool call
- [ ] 移除独立 Tool Model loop（`AgentToolLoop` / `AgentToolLoopRunner`）
- [ ] 流式消费时并发监听 `tool_calls` chunk，异步执行工具
- [ ] Tool 结果追加后触发第二轮流式补充
- [ ] 更新 `lab.toml` 去掉 `tool_model` 配置项

### PR：elaina 角色拆分（memory_bench 多 character 支持）

> 当前 memory_bench 只有 congyin/xnne，vtuber 端是 elaina/xnne，需要两条管道并发写入同一图并实时生成。

- [ ] memory_bench 支持多 character（owner 路由）
- [ ] elaina 作为独立 character 注册
- [ ] 两条管道并发写入兼容性测试

### PR：AIChat 流式 SSE 支持

> 当前 /memory/chat 是 non-stream，攒完整响应返回。流式攒句子延迟更高需要优化。

- [ ] 后端 `/memory/chat` 改为 `StreamingResponse`（SSE）
- [ ] 按标点切割攒句子，降低首包延迟
- [ ] AIChat 前端接入 SSE

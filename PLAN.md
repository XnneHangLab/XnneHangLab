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
- memory_bench 职责纯化：只做记忆存取 + 图谱管线

**架构对齐 #262：**
- memory_bench = 脑子（纯记忆后端）
- src/lab = 身体（Agent 编排、tool loop、prompt 拼装、/chat 端点）

---

## 待做

### 清理 PR（联调验证通过后）

- `memory_bench/server/chat_server.py` 中已移除 chat_router mount，但 standalone 启动器本身可能需要评估是否保留
- prompts/ 目录和 conversations/ 目录仍在 memory_bench 下，后续可考虑迁移到 src/lab 或统一配置

### Plugin 化（#262 Phase 2-4）

- Plugin 注册机制 + ToolPlugin 基类
- Skill 文件系统 + SkillLoader
- Hook 机制 + SystemPromptBuilder + Profile 配置
- memory_bench 封装为 MemoryPlugin

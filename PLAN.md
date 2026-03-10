# PLAN.md

## 当前进行中

### feat/memory-bench-chat-llm-integration (#269 已合入)

memory_bench proxy_router 内嵌到 src/lab，统一配置入口。

**紧急修复待做（见下方 Bug Fix）**

---

## 待做

### Bug Fix：memory_bench LLM 配置回环问题

**问题描述：**

`chat_model.llm_provider = "memory_proxy"` 时，`server.py` 里 `upstream_llm = getattr(lab_settings.agent.llm, chat_model_cfg.llm_provider)` 取到的是 `MemoryProxySetting`（`base_url = localhost:12393`），而不是真实上游（oaipro 等）。

导致：
- `chat_api_key` / `chat_base_url` / `chat_model` 全部读到 memory_proxy 的本地配置
- mem0 事实提取 LLM 也指向 localhost:12393（回环）
- proxy_router 转发目标变成自己 → 死循环

**根本原因：** 用 `chat_model.llm_provider` 同时承担了两个职责：
1. src/lab MemoryAgent chat_llm 用哪个 provider（应该是 memory_proxy）
2. proxy_router 的上游转发目标是哪个 provider（应该是真实 provider）

这两个职责不能用同一个字段表达。

**修复方案：**

在 `[memory_bench]` 块加一个 `upstream_llm_provider` 字段，显式指定 proxy_router 的上游目标：

```toml
[memory_bench]
upstream_llm_provider = "oaipro"   # proxy 转发给哪个真实 provider
user_id = "xnne"
...
```

`server.py` 里改为：
```python
upstream_llm = getattr(lab_settings.agent.llm, memory_bench_cfg.upstream_llm_provider)
```

这样两个职责彻底分离：
- `chat_model.llm_provider = "memory_proxy"` → MemoryAgent 走透明代理
- `memory_bench.upstream_llm_provider = "oaipro"` → proxy 转发到真实 LLM

mem0 事实提取 LLM 也从 `upstream_llm` 取，不再有回环风险。

---

### chat_router 升级（AIChat 完整 Agent 端点）

**目标：** `/memory/chat` 成为 AIChat 的完整 Agent 接口。

**改动：**
- 自有 READ/WRITE/SEARCH/EDIT tool 定义 → 接受外部注入的 ToolManager（src/lab 启动时传入）
- 同步 OpenAI 客户端 → AsyncLLM
- 手动记忆操作 → 直接 import `search_memories()` + `memory_and_graph_background()` from `router.py`
- 调用前召回记忆注入 system prompt，回复后写回

**设计原则：** chat_router 在 memory_bench 内部，直接 import router.py 函数，不走 HTTP。

---

### 清理 PR（#269 联调验证通过后）

删除 `memory_bench/server/` 中已被替代的旧代码：
- `chat_router.py` 旧版 tool 定义（READ/WRITE/SEARCH/EDIT）
- `tools/file_tools.py`
- `tools/search_tools.py`
- `conversation_store.py`（如 chat_router 升级后不再依赖）
- `chat_server.py` 中 `chat_router` 的 mount（保留 proxy_router mount）

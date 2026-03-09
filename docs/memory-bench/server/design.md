# 设计理念

Memory Chat Server 是 Memory Bench 子项目的核心服务，为 AI 角色对话提供**记忆增强**能力。

## 🎯 核心问题

> AI 聊天机器人普遍存在"金鱼记忆"问题——每次对话都从零开始，不记得之前说过什么。

Memory Chat Server 的目标是解决这个问题：让 AI 角色能**真正记住**与用户的交互。

## 📐 职责分离：两个端点，两种哲学

Server 同时服务两种完全不同的调用场景，因此拆分为两个端点，各有清晰的职责边界：

```
Memory Chat Server
├── /v1/chat/completions     ← 透明代理（router.py）
└── /memory/chat             ← 自治 Agent（chat_router.py）
```

### 透明代理 vs 自治 Agent

|  | `/v1/chat/completions` | `/memory/chat` |
|--|----------------------|---------------|
| 📋 **角色** | 透明代理 | 自治 Agent |
| 🎯 **原则** | 调用方感知不到记忆层 | Server 完全掌控 session |
| 👤 **调用方** | `src/lab` Agent（有自己的 MCP、上下文管理） | AIChat 等轻量客户端 |
| 🧠 **记忆** | 仅注入到 system prompt 末尾 | Server 管理对话历史 + 记忆注入 |
| 💬 **上下文** | 调用方负责 | Server 负责（日期 JSON 持久化） |
| 🔧 **工具** | 完整透传（tool_use/tool_result 不过滤） | 内置 READ/WRITE/EDIT/SEARCH |
| 📡 **协议** | OpenAI 兼容 | 简化自定义协议 |

> [!NOTE] 为什么不合并成一个？
> 因为两种调用方的需求本质不同。`src/lab` 的 Agent 已经有完整的工具调用栈（MCP client-server、多图处理），它只需要一个"加了记忆的 LLM 代理"。而 AIChat 是轻量客户端，需要 server 端帮它管理一切。
> 
> 合并会导致两边都做不好：代理不够透明，自治不够彻底。

---

## 🧠 记忆架构

### mem0：记忆的存储与检索

[mem0](https://github.com/mem0ai/mem0) 负责从对话中**自动提取**和**语义检索**记忆：

```
用户消息 → mem0.search() → 相关记忆 → 注入 system prompt
                                          ↓
对话结束 → mem0.add() → 新记忆写入 ← 异步后台
```

**关键设计决策**：
- 搜索结果注入到 system prompt **末尾**，不插入额外 message，不破坏 message 顺序
- 写回只记录 `user` + `assistant` 轮次，工具调用中间步骤不写入
- 事实提取使用自定义 prompt，区分 `[User]` 和 `[Agent]` 前缀

### Neo4j：记忆的图谱化

记忆不只是存起来——通过实时图谱管线，每条记忆都被结构化为知识图谱节点：

```
mem0.add() 返回结果
  ↓
claim_extractor.py → 提取 claim / entity
  ↓
graph_writer.py → Cypher MERGE 写入 Neo4j
  ↓
MemoryItem 节点 → 关联 Character / Scene / Conversation
```

> [!TIP] 图谱管线是可选的（`--enable-graph`），不影响基础对话功能。

---

## 🏗️ System Prompt 拼接

`/memory/chat` 端点不接受客户端传来的 system prompt，而是自己按以下公式拼接：

```
[persona]  base_persona.txt          ← 角色人设（身份、语言、风格）
+
[emotion]  emotion_system.txt        ← EMOTION 格式说明
+
[tool]     tool_definitions.txt      ← 工具定义 + 文件路径认知（可选）
+
[diary]    recent_summary.txt        ← 近期日记总结（可选）
=
完整 system prompt
```

**为什么不让客户端传 system prompt？**

- 同一个 session 里重复注入多份 system prompt 会污染上下文
- 无法统一控制记忆注入的时机和格式
- Server 端拼接可以保证一致性

---

## 🛡️ 安全模型：分级授权

自治 Agent 端点赋予了 LLM 文件操作能力，但严格控制了权限边界：

### 写入：限定在 `memory_bench/` 内部

| 场景 | 默认路径 | 是否需要指定路径 |
|------|----------|:---:|
| 写日记 | `memory_bench/data/diary/YYYY-MM-DD.md` | ❌ |
| 修改 prompt | `memory_bench/server/prompts/...` | ❌ |
| "保存起来" | `memory_bench/data/saved/<auto_name>.md` | ❌ |
| 写特定文件 | 用户指定路径 | ✅（必须在 memory_bench 内） |

### 读取：分层级

| 层级 | 范围 | 说明 |
|------|------|------|
| Level 1 | `memory_bench/` 预设位置 | 无需路径，按 purpose 自动定位 |
| Level 2 | 整个 workspace（只读） | 可以读取仓库任何文件作为参考 |

> [!WARNING] LLM 不能修改 `memory_bench/` 外的任何文件。如果需要修改外部文件，会告诉用户手动操作。

---

## 📦 对话持久化

`/memory/chat` 的对话历史以日期为单位存储为 JSON 文件：

```
memory_bench/conversations/
├── 2026-03-03.json
├── 2026-03-04.json
└── 2026-03-04_02.json    ← 支持手动新开文件
```

每个文件是一个 message 数组：

```json
[
  {"role": "user", "content": "你好", "timestamp": "2026-03-04T08:00:00Z"},
  {"role": "assistant", "content": "你好呀！", "timestamp": "2026-03-04T08:00:01Z"}
]
```

日期 ID 与 Neo4j 的 `conv:YYYY-MM-DD` 节点对齐，确保对话和图谱的时间维度一致。

---

## 🔌 与 `src/lab` 的关系

`src/lab`（主项目）有完整的 Agent 栈。Memory Chat Server 不侵入这些，保持零耦合：

```
src/lab Agent
  │  调用 /v1/chat/completions（换个 base_url 即可）
  │  Agent 完全不知道 memory_bench 的存在
  ▼
Memory Chat Server
  │  注入记忆 → 转发 LLM → 异步写回
  ▼
LLM Provider (OpenAI / OpenRouter / ...)
```

**约定**：
- `src/lab` Agent 只调透明代理端点，不感知内部实现
- 两个端点**不共享** session 状态
- 共用同一个 mem0 实例和 Neo4j graph pipeline（通过 `ServerState`）
- 配置隔离：memory_bench 的配置来自 `.env.benchmark`，不读取 `config/lab.toml`

---

## 📁 代码结构

```
memory_bench/server/
├── chat_server.py          # 独立启动器（CLI + uvicorn）
├── startup.py              # 初始化逻辑（mem0 / OpenAI / 图谱管线）
├── router.py               # 透明代理端点（/v1/chat/completions）
├── chat_router.py          # 自治 Agent 端点（/memory/chat）
├── conversation_store.py   # 日期 JSON 对话持久化
├── claim_extractor.py      # LLM Claim 抽取
├── graph_writer.py         # Neo4j Cypher 写入
├── neo4j_queries.py        # Cypher 语句模板
├── prompts/                # System prompt 模块化文件
│   ├── emotion/
│   ├── tools/
│   └── diary/
└── tools/                  # 内置工具实现
    ├── file_tools.py       # READ / WRITE / EDIT
    └── search_tools.py     # SEARCH
```

---

## 📚 延伸阅读

- [路由与端点](./routes) — 两个端点的详细 API 文档
- [Issue #224](https://github.com/XnneHangLab/XnneHangLab/issues/224) — 原始设计讨论

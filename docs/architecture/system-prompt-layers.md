# System Prompt 分层架构设计

> 本文档描述 src/lab 中 system prompt 的分层组织方式。
> 关联：#262 (Tool/Skill/Plugin 共存架构)

## 设计原则

1. **分层** — 每层职责单一，不混杂
2. **可组合** — 通过 Profile 配置选择加载哪些层
3. **可切换** — 同一层可以有多个实现（如不同角色、不同输出格式）
4. **自动生成优先** — 工具说明、记忆内容由运行时生成，不手写

## 五层模型

```
System Prompt（运行时拼接）
│
├── Layer 1: Persona (角色核心)          [固定，启动时加载]
│   "你是谁、性格怎样、说话风格"
│   └── 每个角色一个文件，Profile 指定加载哪个
│
├── Layer 2: Format (输出格式)           [固定，启动时加载]
│   "回复的结构化格式要求"
│   └── 不同前端需要不同格式，Profile 指定加载哪个
│
├── Layer 3: Skills (能力/策略)          [可插拔，按需加载]
│   "怎么写日记、怎么找文件、怎么使用记忆"
│   └── 每个 Skill 一个 .md 文件，Profile 列出启用哪些
│
├── Layer 4: Tools (工具说明)            [运行时自动生成]
│   "可用工具的 schema 和使用时机"
│   └── ToolManager.build_system_prompt() 自动生成
│
└── Layer 5: Context (动态上下文)        [每次请求注入]
    "记忆召回结果、日记摘要、时间信息"
    └── 运行时从 memory_bench / ConversationStore 获取
```

### 各层详解

#### Layer 1: Persona

角色核心身份。一个文件定义一个角色。

```
prompts/characters/
├── satone.txt      # Satone（さとね）— 写小说的女孩
├── elaina.txt      # 伊蕾娜 — 灰之魔女
├── congyin.txt     # 聪音 — AI 伴侣
└── ...
```

**特点：**
- 纯文本，无格式约束
- 只描述"谁是谁"，不涉及"怎么输出"
- 一个 session 只加载一个 persona

#### Layer 2: Format

输出格式约束。不同前端需要不同格式。

```
prompts/formats/
├── emotion_pipe.txt        # AIChat 格式: [Emotion] ||| TEXT
├── emotion_bracket.txt     # VTuber 格式: [expression] inline in text
├── plain.txt               # 纯文本（无 emotion tag）
└── ...
```

**特点：**
- 约束回复的结构（不是内容）
- 前端决定用哪个格式
- VTuber 的 `live2d_expression_prompt.txt` 属于这一层

**示例：emotion_pipe.txt**
```
【回复格式】
你必须严格按照以下格式回复：
[Emotion] ||| TEXT

可用情感：[Happy] [Sad] [Think] [Wave] ...
```

**示例：emotion_bracket.txt**
```
你可以在回复中使用 [expression] 标签来表达情感。
标签应放在句子开头。支持在一条回复中使用多个标签。

示例："[happy] 你好！今天心情不错呢。"
```

#### Layer 3: Skills

行为策略和知识。AI 阅读后自行执行。

```
prompts/skills/
├── diary_writing.md         # 怎么写日记：格式、存储位置、触发条件
├── file_navigation.md       # 关键文件路径映射、模糊匹配规则
├── memory_strategy.md       # 怎么利用召回的记忆
└── ...
```

**特点：**
- Markdown 格式，可以包含示例和规则
- 不是 function calling schema，是"行为指南"
- 可以按 profile 启用/禁用不同技能

**示例：diary_writing.md**
```markdown
# 日记技能

## 日记存储
- 路径：`data/diary/YYYY-MM-DD.md`
- 格式：Markdown
- 使用 WRITE 工具写入，append 模式

## 触发条件
- 用户说"写日记"/"记录一下"
- 一天结束时的对话总结

## 格式模板
```
### HH:MM
[记录内容]
- 心情：[emotion]
- 关键词：[tags]
```
```

**示例：file_navigation.md**
```markdown
# 文件导航技能

## 关键路径映射
| 用户说 | 实际路径 |
|---|---|
| "人设"/"角色"/"persona" | 当前加载的 persona 文件 |
| "日记"/"diary" | `data/diary/` |
| "记忆"/"memory" | `data/memory/MEMORY.md` |

## 模糊匹配规则
- 用户提到文件名片段 → 先 list_dir 再匹配
- 日期关键词 → 自动转换（"今天" → 当日日期）
```

#### Layer 4: Tools

由 `ToolManager.build_system_prompt()` 运行时自动生成。

**不再手写 tool_definitions.txt。** 工具注册到 ToolManager 后，schema 和 usage_hint 自动拼接。

#### Layer 5: Context

运行时每次请求动态注入。

- **记忆召回**：`search_memories()` → 格式化后注入
- **日记摘要**：最近几天的日记摘要
- **时间信息**：当前日期时间（get_datetime 工具也能提供）

---

## Profile 配置（驱动组合）

```toml
# profiles/congyin_aichat.toml
[prompt]
persona = "characters/congyin.txt"
format = "formats/emotion_pipe.txt"
skills = ["skills/diary_writing.md", "skills/file_navigation.md"]

[tools]
builtin = ["read_file", "write_file", "edit_file", "list_dir", "get_datetime"]
```

```toml
# profiles/elaina_vtuber.toml
[prompt]
persona = "characters/elaina.txt"
format = "formats/emotion_bracket.txt"
skills = []

[tools]
builtin = ["get_datetime"]
```

---

## 拼接顺序（SystemPromptBuilder）

```python
class SystemPromptBuilder:
    """按优先级拼接 system prompt。"""
    
    def build(self) -> str:
        parts = []
        
        # Layer 1: Persona（最高优先级，定义角色身份）
        if self.persona:
            parts.append(self.persona)
        
        # Layer 2: Format（输出格式约束）
        if self.format:
            parts.append(self.format)
        
        # Layer 3: Skills（行为策略）
        for skill in self.skills:
            parts.append(skill)
        
        # Layer 4: Tools（自动生成）
        if self.tool_prompt:
            parts.append(self.tool_prompt)
        
        # Layer 5: Context（动态注入，每次请求不同）
        for ctx in self.contexts:
            parts.append(ctx)
        
        return "\n\n---\n\n".join(parts)
```

---

## 数据目录布局（迁移后）

```
src/lab/
├── prompts/                    # prompt 模板（版本控制）
│   ├── characters/             # Layer 1
│   ├── formats/                # Layer 2
│   └── skills/                 # Layer 3
├── data/                       # 运行时数据（gitignore / 用户数据）
│   ├── diary/                  # 日记文件
│   └── memory/                 # MEMORY.md 等
└── conversation/               # 对话持久化
    └── store.py
```

---

## 迁移映射

| 旧位置 | 新位置 | 层 |
|---|---|---|
| `memory_bench/server/prompts/emotion/base_persona.txt` | `prompts/characters/satone.txt` | L1 |
| `memory_bench/server/prompts/emotion/emotion_system.txt` | `prompts/formats/emotion_pipe.txt` | L2 |
| `memory_bench/server/prompts/tools/tool_definitions.txt` | **删除**（工具 schema 自动生成）+ 文件导航部分提取到 `prompts/skills/file_navigation.md` | L3/L4 |
| `memory_bench/server/prompts/diary/recent_summary.txt` | **删除**（运行时动态生成） | L5 |
| `memory_bench/data/diary/` | `data/diary/` | 数据 |
| `memory_bench/server/memory/MEMORY.md` | `data/memory/MEMORY.md` | 数据 |
| `prompts/characters/elaina.txt` 等 | `prompts/characters/elaina.txt`（位置不变） | L1 |
| `prompts/live2d_expression_prompt.txt` | `prompts/formats/emotion_bracket.txt` | L2 |

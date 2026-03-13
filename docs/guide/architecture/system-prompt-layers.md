# System Prompt 分层架构

> 描述 `src/lab` 中 system prompt 的分层组织方式。  
> 关联：#262（Tool/Skill/Plugin 共存架构）、#278（Profile 配置系统）、#281（Plugin 系统）

## 设计原则

1. **分层**: 每层职责单一，不混杂
2. **可组合**: 通过 Profile 配置选择加载哪些层
3. **可切换**: 同一层可以有多个实现
4. **自动生成优先**: 工具说明由运行时生成，不手写
5. **Context 不污染 System**: 动态上下文注入 user prompt，避免把瞬时信息写进 system prompt

## 五层模型

```text
System Prompt（启动时拼接，固定不变）
│
├── Layer 1: Persona（角色核心）         [固定，启动时加载]
│   “你是谁、性格怎样、说话风格”
│
├── Layer 2: Format（输出格式）          [固定，启动时加载]
│   “回复的结构化格式要求”
│
├── Layer 3: Skills（技能层）            [固定，启动时按 mode 注入]
│   “你有哪些技能、哪些会直接展开、哪些可按需读取”
│   └── inline: 直接注入内容；outline: 注入描述 + 路径
│
└── Layer 4: Tools（工具说明）           [运行时自动生成]
    “可用工具的 schema 和使用时机”
    └── ToolManager.build_system_prompt() 自动生成

============================================================

User Prompt（每轮请求动态注入）

└── Layer 5: Context（动态上下文）       [每次请求，注入 user prompt]
    “记忆召回结果”
    └── 标签块格式：[memory context]...[/memory context]
```

## 各层详解

### Layer 1: Persona

角色核心身份。一个文件定义一个角色，Profile 指定加载哪个。

```text
prompts/characters/
├── satone.md
├── elaina.txt
└── ...
```

- 纯文本，描述“谁是谁”，不涉及“怎么输出”
- 一个 session 只加载一个 persona
- 全量注入，是 system prompt 权重最高的部分

### Layer 2: Format

输出格式约束，不同前端可以复用同一角色但切换不同格式。

```text
prompts/formats/
├── emotion_pipe.md
├── emotion_bracket.md
├── plain.md
└── ...
```

- 约束回复结构，不约束内容本身
- 全量注入

### Layer 3: Skills

技能是 AI 的行为策略和领域知识。当前实现支持两种注入模式：

- `inline`: 启动时直接把 skill 内容展开到 system prompt
- `outline`: 启动时只注入描述和路径，模型需要时再读取 skill 文件

示例：

```text
你有以下技能可按需使用：
- diary: 日记读写相关流程与约定（inline 或 outline，取决于插件声明）
- file_navigation: 在复杂目录中定位文件的策略 -> prompts/skills/file_navigation.md
需要时读取对应文件获取详细指引。
```

这意味着 Layer 3 并不总是“只注入 description + 路径”。较短、常用、希望始终生效的 skill 适合 `inline`；较长、低频、适合按需展开的 skill 适合 `outline`。

日记能力也归属这一层：模型通过 `diary` skill 配合内置 `read_file` / `write_file` 等工具按需读写日记，不走框架自动注入。

### Layer 4: Tools

由 `ToolManager.build_system_prompt()` 在运行时自动生成，不手写。

工具注册到 `ToolManager` 后，`schema` 和 `usage_hint` 会自动拼接为工具说明段。

### Layer 5: Context（注入 user prompt）

每次请求动态生成，**注入 user prompt，不进 system prompt**。

原因：

- system prompt 带有持久语义，容易把过期上下文当成稳定事实
- 动态信息放进 user prompt，更符合“本轮新增信息”的语义
- 可以按轮次更新，不会让 system prompt 逐轮膨胀

格式示例：

```text
[memory context]
今天和聪音聊了关于天气的话题...
上次提到想去图书馆...
[/memory context]

（正文）用户发的消息
```

哪些 context 块被注入，由 Profile 的 `[context]` 配置决定：

```toml
[context]
memory_search = true
```

---

## 拼接实现

```python
Profile.from_toml("profiles/congyin.toml")
    ↓
PluginLoader.load_many(profile.plugins.enabled)
    ↓ tool_plugins, skill_descriptors
    ↓
SystemPromptBuilder.build(
    persona_path=profile.prompt.persona,   # Layer 1
    format_path=profile.prompt.format,     # Layer 2
    skills=skill_descriptors,              # Layer 3（按 inline / outline 注入）
    tool_manager=tool_manager,             # Layer 4（自动生成）
)
    ↓
ContextInjector.build_context_prompt(
    memory_context="...",                  # Layer 5（注入 user prompt）
)
```

核心类：

- `src/lab/profile/system_prompt_builder.py`: 拼接 Layer 1-4
- `src/lab/profile/context_injector.py`: 生成 Layer 5 标签块
- `src/lab/profile/schema.py`: Profile / ContextConfig Pydantic model

---

## 与 Profile 系统的关系

Profile 是驱动五层架构的配置文件，决定：

- 加载哪个 persona / format（Layer 1/2）
- 启用哪些 plugin（tool plugin -> Layer 4，skill plugin -> Layer 3）
- 开启哪些 context 注入（Layer 5）

详见 [Profile 系统](./profile-system)。

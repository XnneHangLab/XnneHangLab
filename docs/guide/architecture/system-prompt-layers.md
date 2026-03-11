# System Prompt 分层架构

> 描述 `src/lab` 中 system prompt 的分层组织方式。
> 关联：#262（Tool/Skill/Plugin 共存架构）、#278（Profile 配置系统）、#281（Plugin 系统）

## 设计原则

1. **分层** — 每层职责单一，不混杂
2. **可组合** — 通过 Profile 配置选择加载哪些层
3. **可切换** — 同一层可以有多个实现（不同角色、不同输出格式）
4. **自动生成优先** — 工具说明由运行时生成，不手写
5. **Context 不污染 System** — 动态上下文注入 user prompt，避免幻觉

## 五层模型

```
System Prompt（启动时拼接，固定不变）
│
├── Layer 1: Persona（角色核心）         [固定，启动时加载]
│   "你是谁、性格怎样、说话风格"
│
├── Layer 2: Format（输出格式）          [固定，启动时加载]
│   "回复的结构化格式要求"
│
├── Layer 3: Skills（技能目录）          [固定，启动时注入 description+路径]
│   "你有哪些技能、它们在哪里"
│   └── 只注入一句话描述 + 文件路径，不展开内容
│
└── Layer 4: Tools（工具说明）           [运行时自动生成]
    "可用工具的 schema 和使用时机"
    └── ToolManager.build_system_prompt() 自动生成

─────────────────────────────────────────────────────────
User Prompt（每轮请求动态注入）

└── Layer 5: Context（动态上下文）       [每次请求，注入 user prompt]
    "记忆召回结果、日记摘要"
    └── 标签块格式：[memory context]...[/memory context]
```

## 各层详解

### Layer 1: Persona

角色核心身份。一个文件定义一个角色，Profile 指定加载哪个。

```
prompts/characters/
├── satone.md       # Satone（さとね）— 写小说的女孩
├── elaina.txt      # 伊蕾娜 — 灰之魔女（VTuber 管线使用）
└── ...
```

- 纯文本，描述"谁是谁"，不涉及"怎么输出"
- 一个 session 只加载一个 persona
- 全量注入，是 system prompt 权重最高的部分

### Layer 2: Format

输出格式约束。不同前端需要不同格式。

```
prompts/formats/
├── emotion_pipe.md         # AIChat 格式：[Emotion] ||| TEXT
├── emotion_bracket.md      # VTuber 格式：[expression] 内联在文本中
├── plain.md                # 纯文本（无 emotion tag）
└── ...
```

- 约束回复的结构，不约束内容
- 全量注入

**emotion_pipe.md 示例：**
```
【回复格式】
你必须严格按照以下格式回复：
[Emotion] ||| TEXT

可用情感：[Happy] [Sad] [Think] [Wave] ...
```

### Layer 3: Skills（懒加载）

技能是 AI 的行为策略和知识。**System prompt 只注入描述和路径，不展开内容。**

```
System Prompt 里注入的内容示例：
你有以下技能可按需调用：
- diary_writing: 日记写作风格与结构指南 → prompts/skills/diary_writing.md
- file_navigation: 在复杂目录中定位文件的策略 → prompts/skills/file_navigation.md
需要时读取对应文件获取详细指引。
```

**为什么懒加载？**

把所有技能文件全量展开注入 system prompt 会导致：
- Persona / Format 等核心信息权重被稀释
- System prompt 膨胀，成本上升
- LLM 注意力分散

懒加载让 LLM 按需读取，在 token 预算有限时优先保证核心身份正确。

技能文件存放在 `src/lab/plugins/` 下，每个 skill plugin 的 `plugin.toml` 里的 `description` 字段就是注入 system prompt 的那一句话。

### Layer 4: Tools

由 `ToolManager.build_system_prompt()` 运行时自动生成，不手写。

工具注册到 ToolManager 后，`schema` 和 `usage_hint` 自动拼接成工具说明段。

### Layer 5: Context（注入 user prompt）

每次请求动态生成，**注入 user prompt，不进 system prompt**。

**为什么不进 system prompt？**

System prompt 有"永久性"语义，LLM 会把里面的信息当成不变的事实。把记忆注入 system prompt 会导致：
- 过期记忆被当成当前事实，产生幻觉
- System prompt 随每轮对话膨胀

注入 user prompt 的语义是"这是本轮的新信息"，更准确，也方便多轮更新。

**格式（标签块）：**

```
[memory context]
今天和聪音聊了关于天气的话题...
上次提到想去图书馆...
[/memory context]

[diary context]
3月11日日记摘要：今天阳光很好...
[/diary context]

（正文）用户发的消息
```

哪些 context 块被注入由 Profile 的 `[context]` 配置决定：

```toml
[context]
memory_search = true   # 注入 [memory context]
diary_summary = false  # 不注入 [diary context]
```

---

## 拼接实现

```
Profile.from_toml("profiles/songyin.toml")
    ↓
PluginLoader.load_many(profile.plugins.enabled)
    → tool_plugins, skill_descriptors
    ↓
SystemPromptBuilder.build(
    persona_path  = profile.prompt.persona,    # Layer 1
    format_path   = profile.prompt.format,     # Layer 2
    skills        = skill_descriptors,         # Layer 3（只注入 description+路径）
    tool_manager  = tool_manager,              # Layer 4（自动生成）
)
    ↓
ContextInjector.build_context_prompt(
    memory_context = "...",   # Layer 5（注入 user prompt）
    diary_context  = "...",
)
```

核心类：
- `src/lab/profile/system_prompt_builder.py` — 拼接 Layer 1-4
- `src/lab/profile/context_injector.py` — 生成 Layer 5 标签块
- `src/lab/profile/schema.py` — Profile / ContextConfig Pydantic model

---

## 与 Profile 系统的关系

Profile 是驱动五层架构的配置文件，决定：
- 加载哪个 persona / format（Layer 1/2）
- 启用哪些 plugin（tool plugin → Layer 4，skill plugin → Layer 3）
- 开启哪些 context 注入（Layer 5）

详见 [Profile 系统](./profile-system)。

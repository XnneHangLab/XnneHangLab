# Skill 系统

Skill 的职责不是“执行动作”，而是“告诉 Agent 该怎么做”。

如果说 tool 是手，那 skill 更像操作手册。它会被注入到 system prompt，影响模型在特定任务里的工作方式。

---

## 什么是 Skill

在 XnneHangLab 里，`skill` 是一种插件类型：

- 不实例化 Python 工具类
- 不直接执行动作
- 由 `PluginLoader` 读取成 `SkillDescriptor`
- 最终交给 `SystemPromptBuilder` 注入 system prompt

```python
@dataclass
class SkillDescriptor:
    id: str
    name: str
    description: str
    files: list[str]
    priority: int
    inline: bool
    requires: list[str]
    plugin_dir: Path
```

这样设计的动机很直接：把“流程知识”和“动作能力”分开。工具负责做事，技能负责告诉模型什么时候做、怎么做更稳。

---

## inline vs outline

Skill 有两种注入方式，核心由 `inline` 决定。

### `inline = true`

直接把 skill 文件内容展开进 system prompt。

```python
inline_skills = [skill for skill in skills if skill.inline]
for skill in sorted(inline_skills, key=lambda item: item.priority):
    for file_path in skill.files:
        content = (skill.plugin_dir / file_path).read_text(encoding="utf-8").strip()
        content = content.replace("{agent_name}", agent_name)
        parts.append(content)
```

这种方式适合规则短、常用、希望模型开局就牢牢记住的技能。

### `inline = false`

不直接展开正文，只注入“你有这些技能可以按需读取”的目录说明。

```python
outline_skills = [skill for skill in skills if not skill.inline]
if outline_skills:
    lines = ["你有以下技能可按需调用："]
    for skill in sorted(outline_skills, key=lambda item: item.priority):
        files_str = ", ".join(str(skill.plugin_dir / file_path) for file_path in skill.files)
        lines.append(f"- {skill.id}: {skill.description} -> {files_str}")
    lines.append("需要时读取对应文件获取详细指引。")
    parts.append("\n".join(lines))
```

这更适合大段说明书，避免把 system prompt 撑得太胖。

---

## 内置 Skills

当前内置的 skill 只有一个：`diary`。

### `diary`

它描述了 diary / memory 文件布局、什么时候该读、什么时候该写，以及如何追加当日流水。

对应 `plugin.toml`：

```toml
[plugin]
id = "diary"
name = "Diary & Memory Skill"
type = "skill"
description = "日记读写策略：目录规范、格式、何时主动记录和回顾"

[type_config]
files = ["skill.md"]
priority = 30
inline = true
requires = ["write_file", "read_file", "list_dir", "get_datetime"]
```

这里的 `requires` 很重要。它不是装饰字段，而是启动时会被校验：如果缺了这些工具，Skill 不应该被启用。

---

## 在 Profile 中启用

Skill 和其他插件一样，也是通过 `profiles/*.toml` 启用。

`profiles/congyin.toml` 里就是一个实际例子：

```toml
[plugins]
enabled = ["web_fetch", "diary", "memory"]
```

只要 `enabled` 里包含 `diary`，`PluginLoader` 就会把它读成 `SkillDescriptor`，再交给 `SystemPromptBuilder` 注入 prompt。

---

## 如何写一个自定义 skill

先写 `plugin.toml`：

```toml
[plugin]
id = "my_skill"
name = "My Skill"
type = "skill"
description = "告诉 Agent 如何完成一类任务"

[type_config]
files = ["skill.md"]
priority = 50
inline = false
requires = ["read_file"]
```

再写 `skill.md`：

```md
# My Skill

先确认目标文件是否存在，再决定是否读取。
如果需要写入，优先保留已有内容，不要盲目覆盖。
```

几个实践建议：

- 规则短而硬的，适合 `inline = true`
- 文档长、步骤多的，适合 `inline = false`
- `requires` 只写真正依赖的工具，不要为了“看起来完整”乱填

Skill 写得好的关键不在于字多，而在于边界清楚。模型最怕的不是规则少，而是规则又长又互相打架。

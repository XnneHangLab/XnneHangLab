# Profile 系统

> `src/lab/profile/` — 配置驱动的系统组装。
> 关联：#278（Profile 配置驱动）、#281（Plugin 系统）

## 设计动机

原来的 `server.py` 硬编码了所有 prompt 路径和工具列表，切换角色或场景需要改 Python 代码。Profile 系统让这一切变成配置：

```toml
# 换个场景，换个文件，不改代码
[prompt]
persona = "prompts/characters/satone.md"
format = "prompts/formats/emotion_pipe.md"

[plugins]
enabled = ["web_search_ddg", "web_fetch"]
```

---

## 文件位置

```
profiles/
├── vtuber.toml        # VTuber 主链路（WebSocket + memory agent，多工具）
├── songyin.toml       # 聪音聊天链路（/memory/chat，读写日记为主）
└── satone_aichat.toml # 示例 profile
```

---

## Profile 格式

```toml
[profile]
name = "songyin"
description = "聪音聊天链路 — /memory/chat，读写日记为主"

[prompt]
persona = "prompts/characters/satone.md"    # Layer 1：角色 persona 文件路径
format = "prompts/formats/emotion_pipe.md"  # Layer 2：输出格式文件路径

[plugins]
enabled = ["web_fetch"]    # 启用的插件 id 列表

[plugins.web_fetch]        # 覆盖 web_fetch 的默认配置（可选）
timeout_s = 15.0

[context]
memory_search = true       # 是否在 user prompt 注入 [memory context]
diary_summary = false      # 是否在 user prompt 注入 [diary context]
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `[profile].name` | str | Profile 唯一名称 |
| `[profile].description` | str | 描述，日志/调试用 |
| `[prompt].persona` | str \| null | 角色文件相对路径（相对于 workspace root）|
| `[prompt].format` | str \| null | 格式文件相对路径 |
| `[plugins].enabled` | list[str] | 按顺序加载的插件 id |
| `[plugins.<id>]` | table | 覆盖对应插件的 `[config]` 默认值 |
| `[context].memory_search` | bool | 开启记忆召回注入 |
| `[context].diary_summary` | bool | 开启日记摘要注入 |

---

## 代码用法

```python
from lab.profile.schema import Profile
from lab.profile.system_prompt_builder import SystemPromptBuilder
from lab.profile.context_injector import ContextInjector
from lab.plugin.loader import PluginLoader

# 1. 加载 Profile
profile = Profile.from_toml(ws_root / "profiles" / "songyin.toml")

# 2. 加载插件
loader = PluginLoader(ws_root)
tool_plugins, skill_descriptors = await loader.load_many(
    profile.plugins.enabled,
    profile_overrides=profile.plugins.overrides,
)

# 3. 注册 tool plugin 到 ToolManager
for plugin in tool_plugins:
    await tool_manager.register_plugin(plugin)

# 4. 构建 system prompt（Layer 1-4）
system_prompt = SystemPromptBuilder(ws_root).build(
    persona_path=profile.prompt.persona,
    format_path=profile.prompt.format,
    skills=skill_descriptors,
    tool_manager=tool_manager,
)

# 5. 每轮请求注入 context（Layer 5，注入 user prompt）
injector = ContextInjector(profile.context)
context_block = injector.build_context_prompt(
    memory_context=recalled_memories,
    diary_context=diary_summary,
)
```

---

## 两条链路

| | **vtuber.toml** | **songyin.toml** |
|---|---|---|
| 入口 | WebSocket（VTuber 管线） | HTTP POST `/memory/chat` |
| 插件 | web_search_ddg, web_fetch, screen_shot | web_fetch |
| Context | memory + diary | memory only |
| 历史存储 | `chat_history/`（VTuber 专用格式） | `conversations/`（日期 JSON） |
| 状态 | 🚧 接管中（PR E） | ✅ 已接管（PR D） |

两条链路的历史存储目录不同，不会冲突。

---

## Profile 加载（from_toml）

```python
profile = Profile.from_toml(Path("profiles/songyin.toml"))
```

`from_toml` 会自动处理 `[plugins.<id>]` 子表，提取为 `overrides` 字典。如果 `persona` / `format` 对应的文件不存在，`SystemPromptBuilder` 会静默跳过，不报错。

---

## 与其他模块的关系

- **Plugin 系统** — Profile 的 `[plugins].enabled` 驱动 PluginLoader，见 [Plugin 系统](./plugin-system)
- **System Prompt 分层** — Profile 决定五层架构的内容，见 [System Prompt 分层](./system-prompt-layers)
- **server.py** — lifespan 里加载 Profile，初始化各条链路

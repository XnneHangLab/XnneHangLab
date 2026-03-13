# Profile 系统

> `src/lab/profile/` 负责用配置装配 persona、format、plugins 与上下文注入策略。
> 本文档对应当前 `config_version = "1.5.0"` 的配置约定。

## 设计动机

Profile 把原本写死在代码里的角色、格式与插件选择下沉到 TOML 配置，方便按场景切换链路：

```toml
[prompt]
persona = "prompts/characters/satone.md"
format = "prompts/formats/emotion_pipe.md"

[plugins]
enabled = ["web_search_ddg", "web_fetch"]
```

---

## 文件位置

```text
profiles/
├── vtuber.toml
├── congyin.toml
└── satone_aichat.toml
```

---

## Profile 格式

下面示例使用当前 `profiles/congyin.toml` 的真实内容：

```toml
[profile]
name = "congyin"
description = "聪音聊天链路 — /memory/chat，读写日记为主"
agent_name = "congyin"

[prompt]
persona = "prompts/characters/satone.md"
format = "prompts/formats/emotion_pipe.md"

[plugins]
enabled = ["web_fetch", "diary", "memory"]

[plugins.web_fetch]
timeout_s = 15.0

[plugins.memory]
user_id = "xnne"
agent_id = "congyin"
search_limit = 10
# base_url 默认 http://localhost:12393，不填即可
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `[profile].name` | str | Profile 唯一名称。 |
| `[profile].agent_name` | str | Agent 标识名，用于数据目录、接口路由等。 |
| `[profile].description` | str | Profile 描述，用于说明链路用途。 |
| `[prompt].persona` | str \| null | persona 文件相对路径，相对于 workspace root。 |
| `[prompt].format` | str \| null | format 文件相对路径。 |
| `[plugins].enabled` | list[str] | 按顺序加载的插件 id。 |
| `[plugins.<id>]` | table | 覆盖对应插件 `plugin.toml [config]` 的默认值。 |
| `hook plugin` 的 `[plugins.<id>]` | table | 覆盖方式与 `tool plugin` 相同，同样通过 `[plugins.<id>]` 注入配置。 |

---

## 代码用法

```python
from lab.plugin.loader import PluginLoader
from lab.profile.context_injector import ContextInjector
from lab.profile.schema import Profile
from lab.profile.system_prompt_builder import SystemPromptBuilder

# 1. 加载 Profile
profile = Profile.from_toml(ws_root / "profiles" / "congyin.toml")

# 2. 加载插件
loader = PluginLoader(ws_root)
tool_plugins, skill_descriptors, hook_plugins = await loader.load_many(
    profile.plugins.enabled,
    profile_overrides=profile.plugins.overrides,
)
# hook_plugins 注册到 HookManager，在每轮 run_turn 前调用

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

# 5. 注入运行时 context（Layer 5）
injector = ContextInjector()
context_block = injector.build_context_prompt(
    memory_context=recalled_memories,
)
```

---

## 两条链路

| | `vtuber.toml` | `congyin.toml` |
|---|---|---|
| 入口 | WebSocket（VTuber 主链路） | HTTP POST `/memory/chat` |
| 插件 | `web_search_ddg`, `web_fetch`, `screen_shot`, `diary` | `web_fetch`, `diary`, `memory` |
| Context | 按 profile 启用的 HookPlugin 注入 | 按 profile 启用的 HookPlugin 注入 |
| 历史存储 | `chat_history/` | `conversations/` |

两条链路的历史目录不同，因此不会互相冲突。

---

## Profile 加载

```python
profile = Profile.from_toml(Path("profiles/congyin.toml"))
```

`from_toml()` 会自动解析 `[plugins.<id>]` 子表，并提取为 `overrides` 字典。如果 `persona` 或 `format` 对应文件不存在，后续由 `SystemPromptBuilder` 做降级处理。

---

## 与其他模块的关系

- Plugin 系统：Profile 通过 `[plugins].enabled` 驱动 `PluginLoader`。
- System Prompt 分层：Profile 决定 persona、format、skills、tools 与 context 的组合方式。
- HookManager：Profile 启用的 `hook plugin` 会在 agent 初始化时注册到 `HookManager`。
- server.py：在应用启动阶段加载 Profile 并初始化对应链路。

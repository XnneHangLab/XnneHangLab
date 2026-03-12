# Profile 系统

> `src/lab/profile/` 是配置驱动的系统组装层。  
> 关联：#278（Profile 配置驱动）、#281（Plugin 系统）

## 设计动机

原来的 `server.py` 硬编码了 prompt 路径和工具列表，切换角色或场景需要改 Python 代码。Profile 系统把这些都收敛为配置：

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

```toml
[profile]
name = "congyin"
description = "聪音聊天链路 - /memory/chat，读写日记为主"
agent_name = "congyin"

[prompt]
persona = "prompts/characters/satone.md"
format = "prompts/formats/emotion_pipe.md"

[plugins]
enabled = ["web_fetch", "diary"]

[plugins.web_fetch]
timeout_s = 15.0
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `[profile].name` | str | Profile 唯一名称 |
| `[profile].agent_name` | str | Agent 标识名，用于 `/data/{agent_name}/` 等路径 |
| `[profile].description` | str | 描述，日志 / 调试用 |
| `[prompt].persona` | str \| null | 角色文件相对路径（相对于 workspace root） |
| `[prompt].format` | str \| null | 格式文件相对路径 |
| `[plugins].enabled` | list[str] | 按顺序加载的插件 id |
| `[plugins.<id>]` | table | 覆盖对应插件的 `[config]` 默认值 |

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
injector = ContextInjector()
context_block = injector.build_context_prompt(
    memory_context=recalled_memories,
)
```

---

## 两条链路

| | **vtuber.toml** | **congyin.toml** |
|---|---|---|
| 入口 | WebSocket（VTuber 管线） | HTTP POST `/memory/chat` |
| 插件 | web_search_ddg, web_fetch, screen_shot, diary | web_fetch, diary |
| Context | HookPlugin 注入（按 profile 启用） | HookPlugin 注入（按 profile 启用） |
| 历史存储 | `chat_history/` | `conversations/` |
| 状态 | 接管中 | 已接管 |

两条链路的历史存储目录不同，不会冲突。

---

## Profile 加载（`from_toml`）

```python
profile = Profile.from_toml(Path("profiles/congyin.toml"))
```

`from_toml` 会自动处理 `[plugins.<id>]` 子表，提取为 `overrides` 字典。如果 `persona` / `format` 对应文件不存在，`SystemPromptBuilder` 会静默跳过，不报错。

---

## 与其他模块的关系

- **Plugin 系统**: Profile 的 `[plugins].enabled` 驱动 `PluginLoader`
- **System Prompt 分层**: Profile 决定五层架构中的 persona、format、skills、tools 和 context 组合
- **server.py**: 在 lifespan 中加载 Profile，初始化各条链路

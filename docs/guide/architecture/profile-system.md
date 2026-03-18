# Profile 系统

> `src/lab/profile/` — 配置驱动的系统组装。
> 关联：#278（Profile 配置驱动）、#281（Plugin 系统）

## 设计动机

原来的 `server.py` 硬编码了所有 prompt 路径和工具列表，切换角色或场景需要改 Python 代码。Profile 系统让这一切变成配置，实现"一份 profile = 一个完整角色"：

- `[prompt]` 负责 persona / format
- `[plugins]` 负责工具和 hook
- `[character]`（可选）负责 VTuber 主链路需要的角色身份、Live2D、显示信息和 TTS 预处理

切换 VTuber 角色时，只需要切换 `memory_agent_profile` 指向的 profile 文件；`/memory/chat` 则继续使用独立的 `memory_chat_profile`。

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
├── elaina.toml   # VTuber 主链路（WebSocket + MemoryAgent），包含 [character]
├── baoqiao.toml  # VTuber 主链路（薄巧），包含 [character]
└── congyin.toml  # /memory/chat 链路，不包含 [character]
```

---

## Profile 格式

### 纯聊天 profile

`congyin.toml` 走 `/memory/chat`，不经过 `websocket_handler` / `chat_history_manager` / Live2D，因此不需要 `[character]`：

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

### VTuber profile

`elaina.toml` 走 WebSocket VTuber 主链路，需要完整 `[character]`：

```toml
[profile]
name = "elaina"
description = "VTuber 主链路 — 多工具，memory agent"
agent_name = "elaina"

[character]
conf_name = "elaina-local"
conf_uid = "elaina-local-001"
live2d_model_name = "Elaina"
character_name = "Elaina"
avatar = "ico_lss.png"
human_name = "Human"

[character.tts_preprocessor]
remove_special_char = true
ignore_brackets = true
ignore_parentheses = true
ignore_asterisks = true
ignore_angle_brackets = true

[prompt]
persona = "prompts/characters/elaina.md"
format = "prompts/formats/emotion_bracket.md"

[plugins]
enabled = ["web_search_ddg", "web_fetch", "screen_shot", "diary", "memory"]
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `[profile].name` | str | Profile 唯一名称 |
| `[profile].agent_name` | str | Agent 标识名，用于 `/data/{agent_name}/` 等路径 |
| `[profile].description` | str | 描述，日志/调试用 |
| `[prompt].persona` | str \| null | 角色文件相对路径（相对于 workspace root）|
| `[prompt].format` | str \| null | 格式文件相对路径 |
| `[plugins].enabled` | list[str] | 按顺序加载的插件 id |
| `[plugins.<id>]` | table | 覆盖对应插件的 `[config]` 默认值（tool / hook plugin 均适用）|
| `[character]` | table \| 不存在 | 可选，仅 VTuber 主链路需要。`memory_agent_profile` 指向的 profile 必须包含此块 |
| `[character].conf_name` | str | 前端角色配置名 |
| `[character].conf_uid` | str | 历史记录与会话使用的角色唯一标识 |
| `[character].live2d_model_name` | str \| null | Live2D 模型名；为空或不填表示不加载 Live2D |
| `[character].character_name` | str | 对话展示使用的角色名 |
| `[character].avatar` | str | 前端头像文件名 |
| `[character].human_name` | str | 人类一侧显示名称 |
| `[character.tts_preprocessor]` | table | VTuber 链路的 TTS 文本预处理配置 |

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

| | `memory_agent_profile`（VTuber） | `memory_chat_profile`（聪音） |
|---|---|---|
| 入口 | WebSocket（VTuber 主链路） | HTTP POST `/memory/chat` |
| 是否需要 `[character]` | **必须** | 不需要 |
| Live2D | 可选（`live2d_model_name` 为空则跳过） | 不使用 |
| 插件 | `web_search_ddg`, `web_fetch`, `screen_shot`, `diary`, `memory` | `web_fetch`, `diary`, `memory` |
| Context | 按 profile 启用的 HookPlugin 注入 | 按 profile 启用的 HookPlugin 注入 |
| 历史存储 | `chat_history/` | `data/conversations/` |

两条链路的历史目录不同，因此不会互相冲突。`memory_agent_profile` 缺少 `[character]` 时，启动校验会直接报错。

---

## Profile 加载

```python
profile = Profile.from_toml(Path("profiles/congyin.toml"))
```

`from_toml()` 会自动解析 `[plugins.<id>]` 子表，并提取为 `overrides` 字典。如果 `persona` 或 `format` 对应文件不存在，后续由 `SystemPromptBuilder` 做降级处理。

可选的 `[character]` 和 `[character.tts_preprocessor]` 嵌套表也会被自动解析：

```python
if profile.character is not None:
    print(profile.character.live2d_model_name)
    print(profile.character.tts_preprocessor.remove_special_char)
```

---

## 与其他模块的关系

- **Plugin 系统** — Profile 的 `[plugins].enabled` 驱动 PluginLoader，见 [Plugin 系统](./plugin-system)
- **System Prompt 分层** — Profile 决定五层架构的内容，见 [System Prompt 分层](./system-prompt-layers)
- **HookManager** — Profile 启用的 hook plugin 会在 agent 初始化时注册到 HookManager，在每轮 `run_turn` 前自动调用
- **ServiceContext** — 启动时从 `memory_agent_profile` 读取 `[character]`，转换成内部 `CharacterSettings`，供 websocket、显示层与 TTS 链路复用
- **WebSocketHandler** — 消费 VTuber profile 的 `character` 信息（conf_uid、avatar、Live2D 模型等）
- **/memory/chat** — 只消费 prompt / plugins，不依赖 `character`
- **server.py** — lifespan 里加载 Profile，初始化各条链路

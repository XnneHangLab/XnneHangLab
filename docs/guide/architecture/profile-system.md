# Profile 系统

> `src/lab/profile/` 负责把 persona、format、plugins，以及可选的 VTuber 角色信息组装成一个完整 profile。

## 设计目标

Profile 现在承载“一份角色 = 一份完整配置”：

- `prompt` 负责 persona / format
- `plugins` 负责工具和 hook
- `character` 负责 VTuber 主链路需要的角色身份、Live2D、显示信息和 TTS 预处理

这样切换 VTuber 角色时，只需要切换 `memory_agent_profile` 指向的 profile 文件；`/memory/chat` 则继续使用独立的 `memory_chat_profile`。

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
description = "聪音聊天链路 - /memory/chat，读写日记为主"
agent_name = "congyin"

[prompt]
persona = "prompts/characters/satone.md"
format = "prompts/formats/emotion_pipe.md"

[plugins]
enabled = ["web_fetch", "diary", "memory"]
```

### VTuber profile

`elaina.toml` 走 WebSocket VTuber 主链路，需要完整 `[character]`：

```toml
[profile]
name = "elaina"
description = "VTuber 主链路 - 多工具，memory agent"
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
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `[profile].name` | str | Profile 名称 |
| `[profile].agent_name` | str | Agent 标识名 |
| `[profile].description` | str | 描述信息 |
| `[prompt].persona` | str \| null | persona 文件路径 |
| `[prompt].format` | str \| null | format 文件路径 |
| `[plugins].enabled` | list[str] | 按顺序启用的插件 id |
| `[plugins.<id>]` | table | 对应插件的覆盖配置 |
| `[character]` | table \| null | 可选，仅 VTuber 主链路需要 |
| `[character].live2d_model_name` | str \| null | `null` 或空字符串表示不加载 Live2D |
| `[character].tts_preprocessor` | table | VTuber 链路的 TTS 预处理配置 |

---

## 代码用法

```python
from pathlib import Path

from lab.profile.schema import Profile

profile = Profile.from_toml(Path("profiles/elaina.toml"))

if profile.character is not None:
    print(profile.character.conf_uid)
```

`Profile.from_toml()` 会自动解析：

- `[prompt]`
- `[plugins]`
- `[plugins.<id>]` 覆盖配置
- 可选的 `[character]` 与 `[character.tts_preprocessor]`

---

## 两条链路

| | `memory_agent_profile` | `memory_chat_profile` |
|---|---|---|
| 入口 | WebSocket VTuber 主链路 | HTTP POST `/memory/chat` |
| 是否需要 `[character]` | 需要 | 不需要 |
| Live2D | 可选，但通常启用 | 不使用 |
| 历史存储 | `chat_history/` | `data/conversations/` |

`memory_agent_profile` 缺少 `[character]` 时，启动校验会直接报错；`memory_chat_profile` 可以是纯 prompt/plugin profile。

---

## 与其他模块的关系

- **Plugin 系统**：`[plugins].enabled` 驱动 `PluginLoader`
- **System Prompt**：`[prompt]` 驱动 `SystemPromptBuilder`
- **ServiceContext**：启动时从 `memory_agent_profile` 读取 `[character]`，再转换成内部 `CharacterSettings`
- **WebSocketHandler**：只消费 VTuber profile 的 `character` 信息
- **/memory/chat**：只消费 prompt / plugins，不依赖 `character`

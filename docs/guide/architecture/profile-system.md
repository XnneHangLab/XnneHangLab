# Profile 系统

> `src/lab/profile/` — 配置驱动的系统组装。
> 关联：#278（Profile 配置驱动）、#281（Plugin 系统）

## 设计动机

原来的 `server.py` 硬编码了 prompt 路径、角色信息和工具列表，切换角色或场景需要改 Python 代码。Profile 系统让这些都变成配置，实现“**一份 profile = 一个完整角色 / 场景**”：

- `[prompt]` 负责 persona / format
- `[plugins]` 负责工具和 hook
- `[character]` 负责 VTuber 主链路需要的角色身份、Live2D、显示信息
- `[character.tts_preprocessor]` 负责 TTS 文本预处理
- `[character.tts]` 负责 GSV 角色名与情绪 → ref_audio 映射

切换 VTuber 角色时，只需要切换 `memory_agent_profile` 指向的 profile 文件；`/memory/chat` 则继续使用独立的 `memory_chat_profile`。

除了直接编辑 `profiles/*.toml`，现在也支持通过可视化页面修改：

- admin 配置页：`http://127.0.0.1:12393/web-tool/admin/`
- 普通 Web 工具页：`http://127.0.0.1:12393/web-tool/`

其中 admin 页适合编辑 profile、插件配置，以及 `[character]` / `[character.tts_preprocessor]` / `[character.tts]` 这类结构化配置。

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
├── baoqiao.toml  # VTuber 主链路（WebSocket + MemoryAgent），包含 [character]
├── elaina.toml   # 旧示例 / 其他 VTuber 主链路
└── congyin.toml  # /memory/chat 链路，可不包含 [character]
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
```

### VTuber profile

VTuber 主链路需要完整 `[character]`，现在推荐写法类似 `baoqiao.toml`：

```toml
[profile]
name = "baoqiao"
description = "VTuber 主链路 — 多工具，memory agent"
agent_name = "baoqiao"

[character]
conf_name = "baoqiao-local"
conf_uid = "baoqiao-local-001"
live2d_model_name = "薄巧_完整版_调用版"
character_name = "薄巧"
avatar = "baoqiao.png"
human_name = "Human"

[character.tts_preprocessor]
remove_special_char = true
ignore_brackets = true
ignore_parentheses = true
ignore_asterisks = true
ignore_angle_brackets = true

[character.tts]
character_name = "baoqiao"

[character.tts.emotions]
default = "emotions/neutral.wav"
开心 = "emotions/happy.wav"
委屈 = "emotions/sad.wav"
生气 = "emotions/angry.wav"

[prompt]
persona = "prompts/characters/baoqiao.md"
format = "prompts/formats/baoqiao_emotion_bracket.md"

[plugins]
enabled = ["web_search_ddg", "web_fetch", "screen_shot", "diary", "memory", "mood_chat"]
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `[profile].name` | str | Profile 唯一名称 |
| `[profile].agent_name` | str | Agent 标识名，用于 `/data/{agent_name}/` 等路径 |
| `[profile].description` | str | 描述，日志/调试用 |
| `[prompt].persona` | str \| null | persona 文件相对路径（相对于 workspace root） |
| `[prompt].format` | str \| null | format 文件相对路径 |
| `[plugins].enabled` | list[str] | 按顺序加载的插件 id |
| `[plugins.<id>]` | table | 覆盖对应插件默认配置 |
| `[character]` | table \| 不存在 | 可选，仅 VTuber 主链路需要。`memory_agent_profile` 指向的 profile 必须包含此块 |
| `[character].conf_name` | str | 前端角色配置名 |
| `[character].conf_uid` | str | 历史记录与会话使用的角色唯一标识 |
| `[character].live2d_model_name` | str \| null | Live2D 模型名；为空或不填表示不加载 Live2D |
| `[character].character_name` | str | 对话展示使用的角色名 |
| `[character].avatar` | str | 前端头像文件名 |
| `[character].human_name` | str | 人类一侧显示名称 |
| `[character.tts_preprocessor]` | table | VTuber 链路的 TTS 文本预处理配置 |
| `[character.tts]` | table | 角色 TTS 配置 |
| `[character.tts].character_name` | str | GSV 服务使用的角色名 / 模型目录名 |
| `[character.tts.emotions]` | map[str, str] | 情绪名到 ref_audio 路径的映射，相对于 `models/gptsovits/<character_name>/` |

---

## 两条链路

| | `memory_agent_profile`（VTuber） | `memory_chat_profile`（聊天） |
|---|---|---|
| 入口 | WebSocket（VTuber 主链路） | HTTP POST `/memory/chat` |
| 是否需要 `[character]` | **必须** | 不需要 |
| Live2D | 可选（`live2d_model_name` 为空则跳过） | 不使用 |
| TTS 角色/情绪配置 | 来自 `[character.tts]` | 不使用 |
| Context | 按 profile 启用的 HookPlugin 注入 | 按 profile 启用的 HookPlugin 注入 |
| 历史存储 | `chat_history/` | `data/conversations/` |

两条链路的历史目录不同，因此不会互相冲突。`memory_agent_profile` 缺少 `[character]` 时，启动校验会直接报错。

---

## Profile 加载

```python
profile = Profile.from_toml(Path("profiles/baoqiao.toml"))

if profile.character is not None:
    print(profile.character.live2d_model_name)
    print(profile.character.tts_preprocessor.remove_special_char)
    print(profile.character.tts.character_name)
    print(profile.character.tts.emotions["default"])
```

`from_toml()` 会自动解析 `[plugins.<id>]` 子表，并提取为 overrides 字典；`[character]`、`[character.tts_preprocessor]`、`[character.tts]` 这些嵌套表也会自动解析。

---

## 与其他模块的关系

- **Plugin 系统** — Profile 的 `[plugins].enabled` 驱动 PluginLoader
- **System Prompt 分层** — Profile 决定 persona / format / tools / skills 的拼装
- **HookManager** — Profile 启用的 hook plugin 会在 agent 初始化时注册
- **ServiceContext** — 启动时从 `memory_agent_profile` 读取 `[character]`，转换成内部 `CharacterSettings`，供 websocket、显示层与 TTS 链路复用
- **TTSManager** — 从 `CharacterSettings.tts_config` 读取 GSV 角色名与情绪映射，按当前 emotion 选择 ref_audio
- **/memory/chat** — 只消费 prompt / plugins，不依赖 `character`

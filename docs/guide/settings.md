# ⚙️ settings.md · lab.toml 配置说明

`lab.toml` 是 **XnneHangLab** 的主配置文件。ASR、WebUI、Agent、服务端口、角色配置，以及各模块开关都会从这里读取。

> 当前配置版本：`v1.5.2`
>
> 配置加载规则：程序会优先在项目 `config/` 下查找配置；找不到会尝试从系统配置目录读取；再找不到会初始化默认配置并写回，保证字段结构完整。

---

## 🌲 配置结构总览

```text
lab.toml
├── conf_version = "v1.5.2"
├── [asr]
│   ├── FFMPEG_PATH
│   ├── device
│   ├── custom_output_dir
│   ├── cache_dir
│   ├── output_dir
│   ├── vad_model_path
│   ├── asr_model_provider
│   ├── punctuation_list
│   ├── cut / cut_line
│   ├── combine / combine_line
│   ├── max_sentence_length
│   ├── [asr.sherpa]
│   │   ├── asr_model_dir
│   │   ├── num_threads
│   │   ├── vad_min_silence_duration
│   │   ├── vad_min_speech_duration
│   │   └── vad_max_speech_duration
│   └── [asr.qwen_asr]
│       ├── model_dir
│       ├── preload_models
│       ├── model_0_6b_path
│       ├── model_1_7b_path
│       ├── device
│       ├── cpu_threads
│       ├── forced_aligner_path
│       └── forced_aligner_device
├── [webui]
│   ├── guide
│   └── subtitle_speed
├── [agent]
│   ├── enable_tool
│   ├── deeplx_api_key
│   ├── user_lang
│   ├── speaker_lang
│   ├── speaker_model
│   ├── faster_first_response
│   ├── max_vision_concurrency
│   ├── require_detailed
│   ├── segment_method
│   ├── interrupt_method
│   ├── memory_agent_profile
│   ├── memory_chat_profile
│   ├── [agent.chat_model]
│   │   ├── llm_provider
│   │   ├── llm_model_name
│   │   └── support_vision
│   ├── [agent.vision_model]
│   │   ├── llm_provider
│   │   └── llm_model_name
│   ├── [agent.embedding]
│   │   ├── api_key
│   │   ├── base_url
│   │   └── model
│   ├── [agent.prompts]
│   │   ├── live2d_expression_prompt
│   │   ├── think_tag_prompt
│   │   ├── character_prompt
│   │   ├── vision_prompt
│   │   └── tool_prompt
│   └── [agent.llm]
│       ├── [agent.llm.openai]
│       ├── [agent.llm.lingyi]
│       ├── [agent.llm.gemini]
│       ├── [agent.llm.oaipro]
│       └── [agent.llm.cerebras]
├── [package]
│   ├── funasr
│   ├── whisper
│   ├── to_do_list
│   ├── yutto_uiya
│   ├── gpt_sovits
│   ├── qwen_tts
│   └── memory_bench
├── [root]
│   └── root_dir
├── [server]
│   ├── host
│   ├── port
│   ├── config_alts_dir
│   └── uvicorn_log_level
├── [vtuber.character_config]
│   ├── conf_name
│   ├── conf_uid
│   ├── live2d_model_name
│   ├── character_name
│   ├── avatar
│   ├── human_name
│   └── [vtuber.character_config.tts_preprocessor_config]
│       ├── remove_special_char
│       ├── ignore_brackets
│       ├── ignore_parentheses
│       ├── ignore_asterisks
│       └── ignore_angle_brackets
└── [memory_bench]
    ├── user_id
    ├── agent_id
    ├── search_limit
    └── server_api_key
```

---

## 📂 配置文件在哪？

### 搜索顺序

1. `./config/<name>.toml`
2. 系统配置目录（Windows: `~/AppData`，Linux/macOS: `~/.config`，或 `XDG_CONFIG_HOME`）
3. 都没有时，自动创建默认配置并写入 `./config/<name>.toml`

### 自动写回

配置会先经过校验与补全：

- 缺少字段：用默认值补齐
- 补齐后会立刻写回，保证你的 `lab.toml` 始终是完整结构

这样做的原因很简单：你不用自己猜字段，也更方便复制一份模板继续改。

---

## 📍 [root] 项目根目录

### root_dir

- 作用：给 Streamlit WebUI 使用的“项目根目录绝对路径”
- 为什么需要它：Streamlit 启动后工作目录可能变化，写进配置后 UI 在任意位置都能稳定找到 `packages/` 等目录

示例：

```toml
[root]
root_dir = "D:\\tmp\\XnneHangLab"
```

---

## 📦 [package] 模块开关

这些布尔值决定某些模块是否启用。

| 配置项 | 默认 | 说明 |
|---|---:|---|
| sherpa_asr | false | 是否启用 Sherpa-ONNX Paraformer ASR 服务 |
| qwen_asr | false | 是否启用 Qwen3-ASR OpenVINO 服务 |
| to_do_list | true | 是否包含 to-do-list 模块 |
| yutto_uiya | true | 是否包含 yutto-uiya 相关 UI/能力 |
| gpt_sovits | true | 是否包含 GPT-SoVITS 能力 |
| qwen_tts | false | 是否包含 Qwen-TTS 能力 |
| memory_bench | false | 是否包含 memory_bench 服务相关能力 |

`sherpa_asr` 和 `qwen_asr` 可以同时开启，服务器会分别注册各自的路由。

示例：

```toml
[package]
sherpa_asr = true
qwen_asr = false
to_do_list = true
yutto_uiya = true
gpt_sovits = true
qwen_tts = false
memory_bench = false
```

---

## 🎤 [asr] 语音识别总配置

`[asr]` 是 ASR 的入口，`asr_model_provider` 决定实际使用的引擎（`sherpa` 或 `qwen_asr`）。具体的引擎参数在 `[asr.sherpa]` 和 `[asr.qwen_asr]` 子段中配置。

### 关键字段

#### FFMPEG_PATH

- 作用：指定 `ffmpeg` 可执行文件路径
- 常见写法：
  - `"ffmpeg"`：走系统 PATH
  - `"C:\\path\\to\\ffmpeg.exe"`：Windows 指向具体 exe

#### device

- 作用：全局推理设备（Sherpa-ONNX 使用）
- 可选值：`"cpu"` / `"cuda"`

#### cache_dir / output_dir

- `cache_dir`：中间缓存目录
- `output_dir`：输出目录

#### vad_model_path

- 作用：Silero VAD 模型路径（供 Sherpa-ONNX 使用）
- 示例：`"./models/silero_vad.onnx"`

#### asr_model_provider

- 作用：选择 VTuber 主路径使用的 ASR 引擎
- 可选值：`"sherpa"` / `"qwen_asr"`

#### cut / cut_line

- `cut = true/false`：是否启用按间隔切分
- `cut_line`：切分间隔（毫秒）

#### combine / combine_line

- `combine = true/false`：是否启用按间隔合并
- `combine_line`：合并间隔（毫秒）

#### max_sentence_length

- 作用：限制最大单句长度

---

### 🦴 [asr.sherpa] Sherpa-ONNX 子配置

基于 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)，使用 Paraformer 模型，速度极快（RTF ≈ 0.007）。

| 配置项 | 说明 |
|---|---|
| asr_model_dir | Paraformer 模型目录 |
| num_threads | 推理线程数 |
| vad_min_silence_duration | VAD 最小静音时长（秒） |
| vad_min_speech_duration | VAD 最小语音时长（秒） |
| vad_max_speech_duration | VAD 最大语音段时长（秒） |

示例：

```toml
[asr.sherpa]
asr_model_dir = "./models/sherpa-onnx-paraformer-zh-2023-09-14"
num_threads = 2
vad_min_silence_duration = 0.25
vad_min_speech_duration = 0.25
vad_max_speech_duration = 8.0
```

---

### 🤖 [asr.qwen_asr] Qwen3-ASR 子配置

基于 Qwen3-ASR OpenVINO INT8 量化，支持 0.6B 和 1.7B 两种模型。

| 配置项 | 说明 |
|---|---|
| model_dir | 模型根目录 |
| preload_models | 启动时预加载的模型列表（`"0.6b"` / `"1.7b"`） |
| model_0_6b_path | Qwen3-ASR 0.6B OpenVINO 模型路径 |
| model_1_7b_path | Qwen3-ASR 1.7B OpenVINO 模型路径 |
| device | OpenVINO 推理设备（`"CPU"` / `"GPU"`） |
| cpu_threads | OpenVINO CPU 线程数（0 = 自动） |
| forced_aligner_path | ForcedAligner 模型路径（空字符串 = 禁用） |
| forced_aligner_device | ForcedAligner 推理设备 |

示例：

```toml
[asr.qwen_asr]
model_dir = "./models"
preload_models = ["0.6b"]
model_0_6b_path = "./models/Qwen3-ASR-0.6B-INT8-OpenVINO"
model_1_7b_path = "./models/Qwen3-ASR-1.7B-INT8-OpenVINO"
device = "CPU"
cpu_threads = 0
forced_aligner_path = ""
forced_aligner_device = "cpu"
```

> **说明**：`preload_models` 控制启动时哪些模型加载进内存，未在列表中的模型首次请求时才加载（会有延迟）。

---

## 🖥️ [webui] Streamlit WebUI 偏好

### guide

- 可选：`open` / `close`
- 作用：是否显示引导

### subtitle_speed

- 可选：`slow` / `normal` / `fast`
- 作用：字幕速度预设

示例：

```toml
[webui]
guide = "open"
subtitle_speed = "normal"
```

---

## 🤖 [agent] LLM Agent

`[agent]` 负责模型选择、工具调用开关、视觉并发、分句策略，以及不同运行场景使用哪个 profile。

### 核心字段

| 字段 | 说明 |
|---|---|
| enable_tool | 是否启用 `BuiltinTool` 工具调用 |
| deeplx_api_key | 跨语种翻译时使用的 DeepLX key |
| user_lang | 用户输入语言 |
| speaker_lang | 语音输出语言 |
| speaker_model | 当前语音模型，默认 `gpt_sovits` |
| faster_first_response | 是否偏向更快首响 |
| max_vision_concurrency | 最大视觉请求并发数 |
| require_detailed | 是否要求更详细的视觉总结 |
| segment_method | 分句方式：`regex` / `pysbd` |
| interrupt_method | 中断信号写入方式：`system` / `user` |
| memory_agent_profile | MemoryAgent 使用的 profile 路径 |
| memory_chat_profile | `/memory/chat` 使用的 profile 路径 |

示例：

```toml
[agent]
enable_tool = true
deeplx_api_key = ""
user_lang = "ZH"
speaker_lang = "EN"
speaker_model = "gpt_sovits"
faster_first_response = false
max_vision_concurrency = 4
require_detailed = true
segment_method = "pysbd"
interrupt_method = "user"
memory_agent_profile = "profiles/elaina.toml"
memory_chat_profile = "profiles/congyin.toml"
```

---

### 💬 [agent.chat_model] 聊天模型选择

| 字段 | 说明 |
|---|---|
| llm_provider | 选用哪个 provider |
| llm_model_name | 聊天模型名 |
| support_vision | 聊天模型是否支持视觉输入 |

```toml
[agent.chat_model]
llm_provider = "oaipro"
llm_model_name = "gpt-5.1-2025-11-13"
support_vision = false
```

---

### 👁️ [agent.vision_model] 视觉模型选择

| 字段 | 说明 |
|---|---|
| llm_provider | 选用哪个 provider |
| llm_model_name | 视觉模型名 |

```toml
[agent.vision_model]
llm_provider = "oaipro"
llm_model_name = "gpt-5.1-2025-11-13"
```

---

### 🔎 [agent.embedding] 向量模型配置

| 字段 | 说明 |
|---|---|
| api_key | Embedding API Key |
| base_url | Embedding 接口地址 |
| model | Embedding 模型名 |

```toml
[agent.embedding]
api_key = ""
base_url = "https://api.oaipro.com/v1"
model = "text-embedding-3-small"
```

---

### 🧠 [agent.prompts] Agent 侧提示词文件

| 字段 | 说明 |
|---|---|
| live2d_expression_prompt | Live2D 表情提示词 |
| think_tag_prompt | think tag 提示词 |
| character_prompt | 角色提示词 |
| vision_prompt | 视觉提示词 |
| tool_prompt | 工具提示词 |

```toml
[agent.prompts]
live2d_expression_prompt = "./prompts/live2d_expression_prompt.txt"
think_tag_prompt = "./prompts/think_tag_prompt.txt"
character_prompt = "./prompts/characters/elaina.txt"
vision_prompt = "./prompts/vision_prompt.txt"
tool_prompt = "./prompts/tool_prompt.txt"
```

---

### 🔌 [agent.llm] Provider 连接配置

每个 provider 结构一致：

- `llm_api_key`
- `llm_base_url`
- `api_format`

你只需要给正在使用的 provider 填好参数即可。

```toml
[agent.llm.openai]
llm_api_key = ""
llm_base_url = "https://api.openai.com/v1"
api_format = "chat_completion"

[agent.llm.oaipro]
llm_api_key = ""
llm_base_url = "https://api.oaipro.com/v1"
api_format = "chat_completion"
```

---

## 🧪 其他顶层配置

这些段落也属于当前 `lab.toml` 的真实结构：

```toml
[server]
host = "localhost"
port = 12393
config_alts_dir = "characters"
uvicorn_log_level = "warning"

[vtuber.character_config]
conf_name = "elaina-local"
conf_uid = "elaina-local-001"
live2d_model_name = "Elaina"
character_name = "Elaina"
avatar = "ico_lss.png"
human_name = "Human"

[vtuber.character_config.tts_preprocessor_config]
remove_special_char = true
ignore_brackets = true
ignore_parentheses = true
ignore_asterisks = true
ignore_angle_brackets = true

[memory_bench]
user_id = "xnne"
agent_id = "congyin"
search_limit = 10
server_api_key = ""
```

---

## ✅ 小建议

- 不要把 API Key 提交到 Git
- 修改配置后建议重启服务，避免运行中的旧配置继续生效
- `profile` 相关角色设定不再从 `lab.toml` 读取，而是走 `profiles/*.toml` 的 `[prompt]`

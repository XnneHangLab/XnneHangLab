# ⚙️ settings.md · lab.toml 配置说明

`lab.toml` 是 **XnneHangLab** 的主配置文件。ASR、WebUI、Agent、服务端口，以及各模块开关都会从这里读取；**角色身份、Live2D、TTS 预处理、GSV 角色与情绪映射** 已迁移到 `profiles/*.toml`。

> 当前配置版本：`v1.6.4`
>
> 配置加载规则：程序会优先在项目 `config/` 下查找配置；找不到会尝试从系统配置目录读取；再找不到会初始化默认配置并写回，保证字段结构完整。

---

## 🌲 配置结构总览

```text
lab.toml
├── conf_version = "v1.6.5"
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
│       ├── gpu_cache_dir
│       ├── forced_aligner_path
│       └── forced_aligner_device
├── [webui]
│   ├── guide
│   └── subtitle_speed
├── [agent]
│   ├── enable_tool
│   ├── translate_provider
│   ├── user_lang
│   ├── speaker_lang
│   ├── faster_first_response
│   ├── max_vision_concurrency
│   ├── require_detailed
│   ├── structured_history_full_turns
│   ├── segment_method
│   ├── interrupt_method
│   ├── memory_agent_profile
│   ├── memory_chat_profile
│   ├── [agent.chat_model]
│   ├── [agent.vision_model]
│   ├── [agent.prompts]
│   │   └── vision_prompt
│   ├── [agent.llm]
│   │   └── [[agent.llm.providers]]
│   ├── [agent.translate.*]
│   ├── [agent.tts]
│   │   └── provider
│   └── [agent.qwen_tts]
│       ├── model_name
│       ├── model_0_6b_path
│       ├── model_1_7b_path
│       ├── device
│       └── warmup_cuda_graphs
├── [local_embedding]
├── [package]
├── [root]
├── [server]
└── [memory_bench]
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

---

## 📍 [root] 项目根目录

### root_dir

- 作用：给 Streamlit WebUI 使用的“项目根目录绝对路径”
- 为什么需要它：Streamlit 启动后工作目录可能变化，写进配置后 UI 在任意位置都能稳定找到 `packages/` 等目录

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
| gsv_lite | false | 是否包含 GSV-Lite 能力 |
| qwen_tts | false | 是否包含 Qwen-TTS 能力 |
| llm_translate | false | 是否启用本地 LLM 翻译引擎 |
| memory_bench | false | 是否包含 memory_bench 服务相关能力 |
| local_embedding | false | 是否启用本地 GGUF Embedding 服务 |

---

## 🤖 [agent] LLM Agent

`[agent]` 负责模型选择、工具调用开关、视觉并发、结构化历史策略，以及不同运行场景使用哪个 profile。

### 核心字段

| 字段 | 说明 |
|---|---|
| enable_tool | 是否启用 `BuiltinTool` 工具调用 |
| translate_provider | 翻译引擎：`"llm"` / `"deeplx"` |
| user_lang | 用户输入语言 |
| speaker_lang | 语音输出语言 |
| faster_first_response | 是否偏向更快首响 |
| max_vision_concurrency | 最大视觉请求并发数 |
| require_detailed | 是否要求更详细的视觉总结 |
| structured_history_full_turns | 最近保留完整结构化历史的轮数 |
| segment_method | 分句方式：`regex` / `pysbd` |
| interrupt_method | 中断信号写入方式：`system` / `user` |
| memory_agent_profile | VTuber 主链路 MemoryAgent 使用的 profile 路径，必须在 profile 中提供 `[character]` |
| memory_chat_profile | `/memory/chat` 使用的 profile 路径，可以不包含 `[character]` |

```toml
[agent]
enable_tool = true
translate_provider = "llm"
user_lang = "ZH"
speaker_lang = "ZH"
faster_first_response = false
max_vision_concurrency = 4
require_detailed = true
structured_history_full_turns = 5
segment_method = "pysbd"
interrupt_method = "user"
memory_agent_profile = "profiles/baoqiao.toml"
memory_chat_profile = "profiles/congyin.toml"
```

### 🔊 [agent.tts]

`[agent.tts]` 负责选择当前 Agent 使用哪个 TTS provider。旧字段 `agent.speaker_model` 仍可被读取并迁移，但保存后会统一写成 `[agent.tts]` 结构。

```toml
[agent.tts]
provider = "gpt_sovits"
```

| 字段 | 说明 |
|---|---|
| provider | 当前 TTS 提供方，支持 `gpt_sovits` / `gsv_lite` / `qwen_tts` |

补充说明：

- 旧配置里的 `speaker_model` 会迁移为 `agent.tts.provider`
- 也可以通过环境变量 `TTS_PROVIDER` 临时覆写该值
- 当前 `AgentSettings.speaker_model` 只是对 `agent.tts.provider` 的兼容属性

### 🗣️ [agent.qwen_tts]

`[agent.qwen_tts]` 负责 Qwen-TTS 自身的模型、路径与加载行为设置；只有当 `package.qwen_tts = true` 且 `agent.tts.provider = "qwen_tts"` 时，这组配置才会真正参与主 TTS 链路。

```toml
[agent.qwen_tts]
model_name = "0.6b"
model_0_6b_path = "./models/Qwen3-TTS-12Hz-0.6B-Base"
model_1_7b_path = "./models/Qwen3-TTS-12Hz-1.7B-Base"
device = "cuda"
warmup_cuda_graphs = true
```

| 字段 | 说明 |
|---|---|
| model_name | 当前使用的 Qwen-TTS 模型规格，支持 `0.6b` / `1.7b` |
| model_0_6b_path | Qwen3-TTS 0.6B 模型目录 |
| model_1_7b_path | Qwen3-TTS 1.7B 模型目录 |
| device | 推理设备；默认 `cuda`，留空时按实现自行检测 |
| warmup_cuda_graphs | 加载后是否预热 CUDA graphs |

使用建议：

- 如果只部署 0.6B，可只保证 `model_0_6b_path` 可用
- 如果切到 `model_name = "1.7b"`，需同步准备 `model_1_7b_path`
- 启用 `package.qwen_tts` 后，配置校验会检查当前激活的 Qwen-TTS 模型路径是否存在

### 💬 [agent.chat_model]

`llm_provider` 不是固定枚举，而是**引用 `[[agent.llm.providers]]` 中某个 `name`**。聊天模型和视觉模型可以共用同一个 provider，也可以分开配置。

```toml
[agent.chat_model]
llm_provider = "openai"
llm_model_name = "gpt-4.1"
support_vision = false
```

### 👁️ [agent.vision_model]

```toml
[agent.vision_model]
llm_provider = "google"
llm_model_name = "gemini-2.0-flash"
```

### 🔌 [agent.llm]

`[agent.llm]` 现在维护的是 provider 注册表，正式结构是 `[[agent.llm.providers]]`。`[agent.chat_model]` 和 `[agent.vision_model]` 只保存“引用哪个 provider”和“使用哪个模型名”。

```toml
[[agent.llm.providers]]
name = "openai"
llm_api_key = ""
llm_base_url = "https://api.openai.com/v1"
api_format = "chat_completion"

[[agent.llm.providers]]
name = "google"
llm_api_key = ""
llm_base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
api_format = "chat_completion"
```

| 字段 | 说明 |
|---|---|
| name | provider 的唯一标识，供 `llm_provider` 引用 |
| llm_api_key | 当前 provider 的 API Key |
| llm_base_url | 当前 provider 的 OpenAI-compatible Base URL |
| api_format | 当前仅支持 `chat_completion` |

补充说明：

- provider 名称必须唯一
- `llm_provider` 负责选择 provider，`llm_model_name` 负责选择模型
- 旧版 `[agent.llm.openai]` / `[agent.llm.google]` 写法仍可被读取，但重新保存后会归一化成 `[[agent.llm.providers]]`

### 🧠 [agent.prompts]

现在 `lab.toml` 里只保留 **全局视觉提示词**：

```toml
[agent.prompts]
vision_prompt = "./prompts/vision_prompt.txt"
```

角色 persona / format 已迁移到 `profiles/*.toml` 的 `[prompt]`；角色相关 TTS 与显示配置也迁移到 `profiles/*.toml` 的 `[character]`。

### 🌍 [agent.translate]

```toml
[agent.translate.deeplx]
api_key = ""

[agent.translate.llm]
model_path = "./models/qwen2.5-0.5b-instruct-q8_0.gguf"
n_gpu_layers = 0
```

---

## 🧩 [local_embedding] 本地 Embedding 服务

```toml
[local_embedding]
model_path = "./models/bge-m3-q8_0.gguf"
pooling_type = "mean"
n_gpu_layers = 0
```

---

## 🧪 其他顶层配置

```toml
[server]
host = "localhost"
port = 12393
config_alts_dir = "characters"
uvicorn_log_level = "warning"

[memory_bench]
search_limit = 10
server_api_key = ""
```

---

## ✅ 现在哪些东西不再放在 `lab.toml`？

以下内容已经迁移到 `profiles/*.toml`：

- 角色身份：`conf_name` / `conf_uid` / `character_name` / `avatar` / `human_name`
- Live2D：`live2d_model_name`
- TTS 文本预处理：`[character.tts_preprocessor]`
- GSV 角色与情绪映射：`[character.tts]` / `[character.tts.emotions]`
- Persona / format prompt：`[prompt]`
- 具体插件启用与插件覆写：`[plugins]`

也就是说：

- `lab.toml` 负责**全局运行时设置**
- `profiles/*.toml` 负责**角色 / 场景 / 插件 / prompt / TTS 个性化配置**

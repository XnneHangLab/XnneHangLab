# ⚙️ settings.md · lab.toml 配置说明

`lab.toml` 是 **XnneHangLab** 的主配置文件。ASR、WebUI、Agent、服务端口，以及各模块开关都会从这里读取；**角色身份、Live2D、TTS 预处理、GSV 角色与情绪映射** 已迁移到 `profiles/*.toml`。

> 当前配置版本：`v1.6.5`
>
> 配置加载规则：程序会优先在项目 `config/` 下查找配置；找不到会尝试从系统配置目录读取；再找不到时仅使用内存默认值。读取配置不会创建、补全或改写文件；显式保存或执行 `just reload-lab-setting` 才会写入配置。

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
│   ├── structured_history_full_turns
│   ├── segment_method
│   ├── interrupt_method
│   ├── memory_agent_profile
│   ├── memory_chat_profile
│   ├── [agent.chat_model]
│   ├── [agent.llm]
│   │   └── [[agent.llm.providers]]
│   ├── [agent.translate.*]
│   ├── [agent.tts]
│   │   ├── provider
│   │   ├── voice_assets_root
│   │   ├── [agent.tts.gsv_lite]
│   │   │   └── use_bert
│   │   └── [agent.tts.genie_tts]
│   │       ├── language
│   │       ├── use_roberta
│   │       └── onnx_intra_threads
│   └── [agent.qwen_tts]
│       ├── model_name
│       ├── model_0_6b_path
│       ├── model_1_7b_path
│       ├── device
│       └── warmup_cuda_graphs
├── [local_embedding]
├── [package]
├── [root]
└── [server]
```

---

## 📂 配置文件在哪？

### 搜索顺序

1. `./config/<name>.toml`
2. 系统配置目录（Windows: `~/AppData`，Linux/macOS: `~/.config`，或 `XDG_CONFIG_HOME`）
3. 都没有时，只在内存中使用默认配置；不会创建文件。

### 读取与写入

配置读取会完成 Pydantic 校验和内存中的默认值/兼容字段归一化，但不会修改磁盘。只有 Launcher 保存设置或显式执行 `just reload-lab-setting` 才会生成、迁移或写回 TOML。

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
| gsv_lite | false | 是否包含 GSV-Lite 能力 |
| genie_tts | false | 是否包含 Genie-TTS 能力 |
| qwen_tts | false | 是否包含 Qwen-TTS 能力 |
| llm_translate | false | 是否启用本地 LLM 翻译引擎 |
| local_embedding | false | 是否启用本地 GGUF Embedding 服务 |

---

## 🤖 [agent] LLM Agent

`[agent]` 负责模型选择、工具调用开关、结构化历史策略，以及不同运行场景使用哪个 profile。

### 核心字段

| 字段 | 说明 |
|---|---|
| enable_tool | 是否启用 `BuiltinTool` 工具调用 |
| translate_provider | 翻译引擎：`"llm"` / `"deeplx"` |
| user_lang | 用户输入语言 |
| speaker_lang | 语音输出语言 |
| faster_first_response | 是否偏向更快首响 |
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
structured_history_full_turns = 5
segment_method = "pysbd"
interrupt_method = "user"
memory_agent_profile = "profiles/baoqiao.toml"
memory_chat_profile = "profiles/congyin.toml"
```

### 🔊 [agent.tts]

`[agent.tts]` 负责选择当前 Agent 使用哪个 TTS provider。默认值为 `none`；旧字段 `agent.speaker_model` 仍可被读取并迁移，但保存后会统一写成 `[agent.tts]` 结构。

```toml
[agent.tts]
provider = "none"
```

| 字段 | 说明 |
|---|---|
| provider | 当前 TTS 提供方，支持 `none` / `genie_tts` / `gsv_lite` / `qwen_tts`；`none` 会覆盖角色 profile 中的语音引擎并跳过本地 TTS 加载 |

补充说明：

- 旧配置里的 `speaker_model` 会迁移为 `agent.tts.provider`
- 也可以通过环境变量 `TTS_PROVIDER` 临时覆写该值
- 当前 `AgentSettings.speaker_model` 只是对 `agent.tts.provider` 的兼容属性

### 🧠 [agent.tts.gsv_lite]

`[agent.tts.gsv_lite]` 用于配置 GSV-Lite 的额外推理选项。

```toml
[agent.tts.gsv_lite]
use_bert = false
```

| 字段 | 说明 |
|---|---|
| use_bert | 是否启用中文 BERT 特征。开启后通常能显著改善中文停顿、重音和句子节奏；但对日文 / 英文或混合文本，可能会带来不自然的语气起伏。 |

使用建议：

- **中文推理建议开启**：不开时中文容易出现停顿、生硬重音或“大佐味”
- **日文 / 英文推理建议关闭**：避免语气起伏异常或整体韵律不自然
- 如果当前角色主要说中文，可以在配置中默认开启；如果主要说日文 / 英文，建议保持关闭

### 🗣️ [agent.tts.genie_tts]

`[agent.tts.genie_tts]` 用于配置 Genie-TTS 的语言、RoBERTa 与 ONNX 推理线程数。只有当 `package.genie_tts = true` 且 `agent.tts.provider = "genie_tts"` 时，这组配置才会真正参与主 TTS 链路。

```toml
[agent.tts.genie_tts]
language = "auto"
use_roberta = false
onnx_intra_threads = 4
```

| 字段 | 说明 |
|---|---|
| language | 语言覆写。支持 `Chinese` / `English` / `Japanese` / `Hybrid-Chinese-English` / `Korean` / `auto`；`auto` 时优先读取角色目录的 `infer.json` |
| use_roberta | 是否启用中文 RoBERTa 特征，改善中文停顿与语气。需要在 `models/geniedata/` 下安装对应资源 |
| onnx_intra_threads | 分配给每个 ONNX 会话的 CPU 线程数（`intra_op_num_threads`）。设为 `0` 由 ONNX Runtime 自行决定；推荐设为 `4` 保持 CPU 资源常驻，避免冷推理导致首帧延迟突增。对应环境变量 `TTS_GENIE_TTS_ONNX_INTRA_THREADS` |

使用建议：

- **建议保持 `onnx_intra_threads = 4`**：设为 0 时 ONNX Runtime 可能在空闲后释放 CPU 资源，导致偶发单次推理超过 10s 的冷推理现象
- **中文角色建议开启 `use_roberta`**：前提是已安装 RoBERTa 资源（运行 `just install-genie-data`）
- **`language` 大多数情况保持 `auto`**：有需要时再显式指定语言，以匹配角色模型的训练语言

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

`llm_provider` 不是固定枚举，而是**引用 `[[agent.llm.providers]]` 中某个 `name`**。需要看图时，请选择支持视觉的聊天模型并开启 `support_vision`。

```toml
[agent.chat_model]
llm_provider = "deepseek"
llm_model_name = "deepseek-v4-flash-vision-exp"
support_vision = true
thinking_mode = "disabled"
```

| 字段 | 说明 |
|---|---|
| support_vision | 开启时，文本与原图直接进入主模型请求；关闭时明确提示无法分析图片，后台游戏观察不启动 |
| thinking_mode | `default` 不发送提供商扩展参数；`enabled` / `disabled` 显式开关支持 thinking 参数的模型。DeepSeek 实时视觉交互建议使用 `disabled` |

### 🔌 [agent.llm]

`[agent.llm]` 维护 provider 注册表，正式结构是 `[[agent.llm.providers]]`。`[agent.chat_model]` 保存 provider 引用和模型名。

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

角色 persona / format 位于 `profiles/*.toml` 的 `[prompt]`；角色相关 TTS 与显示配置位于 `[character]`。

旧配置中的 `agent.vision_model`、`agent.prompts`、`max_vision_concurrency` 和 `require_detailed` 已移除。加载时会忽略这些字段，读取不会改写本地文件，显式保存后将清除这些字段。

### 按需看屏幕与 OCR

角色 profile 启用 `screen_shot` 后，用户可请求新鲜截图。需要准确读取字幕、台词时，可在该 profile 中启用独立 OCR 工具：

```toml
[plugins.screen_shot]
enable_ocr = true
ocr_threads = 2
```

默认关闭 OCR；截图交付始终不等待 OCR。`screen_ocr` 会单独采集一帧并返回采集标识、UTC 时间和识别文字，不能将其文字当作先前截图的内容。OCR 在本次工具请求中执行，取消后不会补发结果；原生识别可能继续计算到返回，其间同一工具拒绝重复 OCR 请求。没有后台采样、待处理帧队列或视觉主动发言。旧 profile 中的 `visual_observer` 和 mood_chat 的游戏模式字段加载时兼容忽略；普通 mood_chat 保持独立运行。

### 按需回顾最近画面

在 Windows 的 WebSocket 会话中启用 `screen_shot` 插件后，可按用户明确要求调用 `screen_record`，无需新增 Launcher 设置。工具参数示例：

```json
{"action": "start", "seconds": 30, "fps": 2, "max_frames": 24}
```

这会在内存中记录最近画面，不自动发言。之后用 `{"action":"review","seconds":15,"review_frames":4}` 获取已有时间窗中的关键帧拼图，用 `status` 查询、`stop` 停止并清空。没有提前开启记录就没有过去的画面；看当前画面仍使用新鲜的 `screen_shot`。采集使用 `[asr].FFMPEG_PATH`，缺失或不支持时明确失败，不影响 Pillow 截图。

完整参数、缓存预算、会话清理和上游维护约定见源码旁的 `src/lab/plugins/screen_shot/DESIGN.md`。首版仅支持 Windows WebSocket 会话的记录，HTTP 共享聊天上下文不启动采集。

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

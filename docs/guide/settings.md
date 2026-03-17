# settings.md

`config/lab.toml` 是 XnneHangLab 的主配置文件。ASR、Agent、服务端口、VTuber 角色配置，以及各模块开关都从这里读取。

当前配置版本：`v1.5.5`

## 配置树

```text
lab.toml
├── conf_version
├── [asr]
│   ├── ...
│   ├── [asr.sherpa]
│   └── [asr.qwen_asr]
├── [webui]
├── [agent]
│   ├── enable_tool
│   ├── translate_provider
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
│   ├── [agent.vision_model]
│   ├── [agent.prompts]
│   ├── [agent.llm.*]
│   └── [agent.translate]
├── [local_embedding]
├── [package]
├── [root]
├── [server]
├── [vtuber.character_config]
│   └── [vtuber.character_config.tts_preprocessor_config]
└── [memory_bench]
```

## 配置加载规则

程序按以下顺序查找配置：

1. `./config/<name>.toml`
2. 系统配置目录
3. 如果都不存在，则自动创建默认配置并写回 `./config/<name>.toml`

## [package] 模块开关

| 字段 | 默认值 | 说明 |
|---|---:|---|
| `sherpa_asr` | `false` | 启用 Sherpa-ONNX ASR |
| `qwen_asr` | `false` | 启用 Qwen3-ASR |
| `llm_translate` | `false` | 启用本地 LLM 翻译 |
| `local_embedding` | `false` | 启用本地 GGUF Embedding 服务 |
| `to_do_list` | `true` | 启用 todo 模块 |
| `yutto_uiya` | `true` | 启用 yutto-uiya |
| `gpt_sovits` | `true` | 启用 GPT-SoVITS |
| `qwen_tts` | `false` | 启用 faster-qwen-tts |
| `memory_bench` | `false` | 挂载 memory_bench 后端 |

示例：

```toml
[package]
sherpa_asr = false
qwen_asr = false
llm_translate = false
local_embedding = true
to_do_list = true
yutto_uiya = true
gpt_sovits = true
qwen_tts = false
memory_bench = true
```

## [agent] 重点字段

`[agent]` 负责聊天模型、视觉模型、翻译策略、角色 profile 和工具调用开关。

### [agent.chat_model]

```toml
[agent.chat_model]
llm_provider = "oaipro"
llm_model_name = "gpt-5.1-2025-11-13"
support_vision = false
```

### [agent.vision_model]

```toml
[agent.vision_model]
llm_provider = "oaipro"
llm_model_name = "gpt-5.1-2025-11-13"
```

### [agent.translate]

```toml
[agent]
translate_provider = "llm"  # "llm" | "deeplx"

[agent.translate.deeplx]
api_key = ""

[agent.translate.llm]
model_path = "./models/qwen2.5-0.5b-instruct-q8_0.gguf"
n_gpu_layers = 0
```

## [local_embedding] 本地 Embedding

XnneHangLab 现在支持把 GGUF embedding 模型直接挂到现有 FastAPI 服务上，对外暴露 OpenAI 兼容的 `POST /v1/embeddings`。

```toml
[local_embedding]
model_path = "./models/bge-m3-q8_0.gguf"
pooling_type = "mean"
n_gpu_layers = 0
```

字段说明：

| 字段 | 说明 |
|---|---|
| `model_path` | 本地 GGUF embedding 模型路径 |
| `pooling_type` | `mean` / `cls` / `last` |
| `n_gpu_layers` | GPU 卸载层数，`0` 表示纯 CPU |

下载模型：

```bash
just download-local-embedding
```

验证端点：

```bash
just test-embedding
```

说明：

- `memory_bench` 会自动使用本地 embedding 服务，无需再配置远程 embedding API。
- 本地 embedding 端点默认和主 FastAPI 服务共用同一个端口。
- 更换 embedding 模型后，旧的 Qdrant 向量数据不兼容，需要重建。

## [memory_bench]

```toml
[memory_bench]
search_limit = 10
server_api_key = ""
```

说明：

- 开启 `memory_bench` 时，必须同时开启 `package.local_embedding = true`
- 启动前会校验 `[local_embedding].model_path` 指向的模型文件是否存在

## 典型示例

```toml
[package]
local_embedding = true
memory_bench = true

[local_embedding]
model_path = "./models/bge-m3-q8_0.gguf"
pooling_type = "mean"
n_gpu_layers = 0

[memory_bench]
search_limit = 10
server_api_key = ""
```

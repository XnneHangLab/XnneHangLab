# API 模块

`src/lab/api/` — HTTP 路由、外部服务客户端、业务逻辑封装。

## 目录结构

```
api/
├── types.py             # 内部类型定义
├── routes/              # FastAPI 路由（协议层）
│   ├── asr_sherpa.py    # /asr/sherpa — Sherpa-ONNX Paraformer 识别 + VAD
│   ├── asr_qwen.py      # /asr/qwen-asr — Qwen3-ASR OpenVINO 识别
│   ├── asr_reload.py    # /asr/reload、/asr/sherpa/reload — ASR 热重载
│   ├── asr_shared.py    # 共享工具（文件上传暂存、路径处理）
│   ├── deeplx.py        # /translate — DeepLX 翻译代理
│   ├── faster_qwen_tts.py  # /tts/qwen-tts — Qwen-TTS 合成
│   ├── gpt_sovits.py    # /tts/gptsovits — GPT-SoVITS v1
│   ├── gpt_sovits_v2.py # /tts/gptsovitsv2 — GPT-SoVITS v2
│   └── vtuber.py        # /client-ws — VTuber WebSocket 入口
├── logic/               # 业务逻辑与模型封装
│   ├── sherpa_asr.py    # Sherpa-ONNX 引擎单例管理（加载 / 热重载 / 推理封装）
│   ├── qwen_asr.py      # Qwen3-ASR 引擎单例管理（加载 / 热重载 / 推理封装）
│   └── faster_qwen_tts.py  # Qwen-TTS 合成逻辑（单次 / 流式）
└── clients/             # 外部服务客户端
    ├── base_client_interface.py  # BaseRequest / BaseResponse / BaseClientInterface
    ├── asr_client.py        # ASRClient
    ├── gpt_sovits_client.py # GPTSoVITSClient
    ├── deeplx_client.py     # DeepLXClient
    ├── reload_client.py     # ReloadClient（模型热重载）
    └── vad_client.py        # VADClient
```

## 职责划分

### Routes — 协议层

路由只负责 HTTP 协议处理（参数解析、响应格式化），业务逻辑委托给 `logic/`。

| 路由 | 前缀 | 功能 |
|------|------|------|
| `asr_sherpa.py` | `/asr/sherpa` | Sherpa-ONNX Paraformer 语音识别（transcribe + VAD） |
| `asr_qwen.py` | `/asr/qwen-asr` | Qwen3-ASR OpenVINO 识别（0.6B / 1.7B 各自一个端点） |
| `asr_reload.py` | `/asr` | ASR 热重载（`/reload` 全量 + `/sherpa/reload` 单独） |
| `asr_shared.py` | — | 上传文件暂存到缓存目录，`file_default` 依赖注入 |
| `deeplx.py` | `/translate/deeplx` | DeepLX 翻译代理（调用外部服务） |
| `llm_translate.py` | `/translate/llm` | 本地 LLM 翻译（Qwen2.5-0.5B Q8 GGUF，llama-cpp-python） |
| `faster_qwen_tts.py` | `/tts/qwen-tts` | Qwen-TTS 语音合成（非流式 + SSE 流式） |
| `gpt_sovits.py` | `/tts/gptsovits` | GPT-SoVITS v1 TTS（JSON → base64 音频） |
| `gpt_sovits_v2.py` | `/tts/gptsovitsv2` | GPT-SoVITS v2 TTS（GET/POST → 音频文件，支持流式） |
| `vtuber.py` | `/client-ws` | Open-LLM-VTuber WebSocket 连接管理 |

### Logic — 模型封装

每个文件对应一套引擎，同时包含单例管理和推理封装，职责内聚：

| 文件 | 内容 |
|------|------|
| `logic/sherpa_asr.py` | `load_sherpa_asr` / `reload_sherpa_asr` / `sherpa_asr_audio` / `sherpa_vad_audio`。启动时预加载 Paraformer + Silero VAD，热重载先 reset 再重新加载。 |
| `logic/qwen_asr.py` | `load_qwen_asr_engine` / `reload_qwen_asr_engine` / `qwen_asr_transcribe` / `preload_configured_qwen_asr_engines`。支持多模型并发（0.6B / 1.7B 各自独立单例）。`normalize_qwen_model_name` 处理路由层传入的各种别名。 |
| `logic/faster_qwen_tts.py` | Qwen-TTS 合成逻辑（单次 / 流式） |
| `logic/llm_translate.py` | LLMTranslateEngine 加载/卸载/路径解析 |
| `logic/translate.py` | `TranslateEngineRouter`：按 `translate_provider` 路由到 DeepLX 或本地 LLM |

Sherpa-ONNX 与 Qwen3-ASR 完全解耦，`server.py` 启动时各自按 `[package]` flag 独立预加载，互不干扰。

### Clients — 外部服务封装

所有 Client 继承 `BaseClientInterface`，统一了请求/响应模型和日志。用于从 `conversations/` 等内部模块调用 TTS、ASR 等服务。

## 与其他模块的关系

- **server.py** 按 `[package]` 开关挂载路由：`sherpa_router`、`qwen_asr_router`、`asr_reload_router`、`deeplx_router`、`llm_translate_router`（`llm_translate=true`）、`qwen_tts_router`、`vtuber_router`
- **conversations/** 通过 Clients 调用 TTS / 翻译
- **agent/** 不直接依赖 api/，而是通过 conversations 层间接使用

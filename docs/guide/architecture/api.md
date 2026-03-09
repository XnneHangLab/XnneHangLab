# API 模块

`src/lab/api/` — HTTP 路由、外部服务客户端、模型加载。

## 目录结构

```
api/
├── types.py             # 内部类型（FunASRModels / GlobalModelContainer）
├── routes/              # FastAPI 路由
│   ├── asr.py           # /asr — 语音识别（FunASR / Whisper）
│   ├── deeplx.py        # /translate — DeepLX 翻译代理
│   ├── faster_qwen_tts.py  # /tts/qwen-tts — Qwen-TTS 合成
│   ├── gpt_sovits.py    # GPT-SoVITS v1 路由
│   ├── gpt_sovits_v2.py # GPT-SoVITS v2 路由
│   └── vtuber.py        # VTuber WebSocket 入口
├── logic/               # 业务逻辑与模型封装
│   ├── funasr.py        # FunASRModel + 单例管理（load / reload / 推理封装）
│   ├── whisper.py       # WhisperModel + 单例管理（load / reload / 推理封装）
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
| `asr.py` | `/asr` | FunASR / Whisper 语音识别（带标点 / 不带标点 / VAD / 模型热重载） |
| `deeplx.py` | `/translate/deeplx` | DeepLX 翻译代理（调用外部服务） |
| `faster_qwen_tts.py` | `/tts/qwen-tts` | Qwen-TTS 语音合成（非流式 + SSE 流式） |
| `gpt_sovits.py` | `/tts/gptsovits` | GPT-SoVITS v1 TTS（JSON → base64 音频） |
| `gpt_sovits_v2.py` | `/tts/gptsovitsv2` | GPT-SoVITS v2 TTS（GET/POST → 音频文件，支持流式） |
| `vtuber.py` | `/client-ws` | Open-LLM-VTuber WebSocket 连接管理 |

### Logic — 模型封装

每个文件对应一个模型，同时包含模型类定义和单例管理函数，职责内聚：

| 文件 | 内容 |
|------|------|
| `logic/funasr.py` | `FunASRModel`（asr / vad / asr_no_punc 三种子模型）+ `load_funasr` / `reload_funasr` / `funasr_asr_audio` / `funasr_vad_audio` |
| `logic/whisper.py` | `WhisperModel` + `load_whisper` / `reload_whisper` / `whisper_asr_audio` |
| `logic/faster_qwen_tts.py` | Qwen-TTS 合成逻辑（单次 / 流式） |

FunASR 与 Whisper 完全解耦，`server.py` 启动时各自按 `[package]` flag 独立预加载，互不干扰。

### Clients — 外部服务封装

所有 Client 继承 `BaseClientInterface`，统一了请求/响应模型和日志。用于从 `conversations/` 等内部模块调用 TTS、ASR 等服务。

## 与其他模块的关系

- **server.py** 挂载路由：`deeplx_router`、`qwen_tts_router`、`vtuber_router`
- **conversations/** 通过 Clients 调用 TTS / 翻译
- **agent/** 不直接依赖 api/，而是通过 conversations 层间接使用

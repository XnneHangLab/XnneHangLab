# ASR 模块

`src/lab/asr/` — 语音识别（FunASR / Whisper）。

## 目录结构

```
asr/
├── asr_base_model.py    # ASRBaseModel 抽象基类
├── combiner.py          # 句子合并（短间隔句子拼接）
├── cutter.py            # 句子切分（长停顿处拆句）
├── funasr/
│   ├── method.py        # FunASR 推理（ASR + VAD + 标点恢复）
│   ├── extractor.py     # 结果解析与结构化
│   ├── converter.py     # ASR Response → Sentence 转换
│   └── model.py         # FunASR 模型定义
└── whisper/
    └── converter.py     # Whisper Response → Sentence 转换
```

## 核心概念

### ASRBaseModel

抽象基类，定义三个接口：
- `init_model()` — 加载模型权重
- `reload_model()` — 热重载
- `forward(input_path)` — 推理

`FunASRModel` 和 `WhisperModel`（定义在 `api/model.py`）实现此接口。

### 句子后处理

ASR 输出的原始句子需要经过后处理才能用于字幕显示：

1. **Cutter** — 根据 `cut_line`（停顿阈值）将长句拆成短句
2. **Combiner** — 根据 `combine_line` 将间隔过短的句子合并

两者互为反向操作，建议只启用其中一个。如果同时启用，需要 `combine_line > cut_line`。

### 数据结构

ASR 结果统一为 `Sentence` 结构（定义在 `_typing.py`），包含：
- 文本内容
- 词级时间戳（`Word` 列表）
- 起止时间

FunASR 和 Whisper 各自的 converter 负责将原始格式转为统一的 `Sentence`。

## 与其他模块的关系

- **api/core_logic.py** 调用 ASR 模型进行推理
- **api/routes/asr.py** 暴露 HTTP 接口
- **api/clients/asr_client.py** 提供客户端封装

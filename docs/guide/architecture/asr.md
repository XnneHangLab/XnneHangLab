# ASR 模块

`src/lab/asr/` — 语音识别，当前支持 **Sherpa-ONNX Paraformer** 和 **Qwen3-ASR（OpenVINO INT8）** 两套引擎。

## 目录结构

```
asr/
├── asr_base_model.py    # ASRBaseModel 抽象基类
├── combiner.py          # 句子合并（短间隔句子拼接）
├── converter.py         # 通用结果转换工具
├── cutter.py            # 句子切分（长停顿处拆句）
├── types.py             # 共享类型定义（Sentence / Word）
├── sherpa/
│   ├── engine.py        # Sherpa-ONNX Paraformer 推理引擎
│   ├── probe.py         # 模型探测与验证
│   └── utils.py         # 音频预处理工具
└── qwen_asr/
    ├── engine.py        # Qwen3-ASR OpenVINO 推理引擎（支持 0.6B / 1.7B）
    ├── processor.py     # 音频预处理（特征提取）
    └── forced_aligner.py # ForcedAligner（词级时间戳对齐，可选）
```

## 核心概念

### ASRBaseModel

抽象基类，定义三个接口：
- `init_model()` — 加载模型权重
- `reload_model()` — 热重载
- `forward(input_path)` — 推理

`sherpa/engine.py` 中的 Sherpa 引擎和 `qwen_asr/engine.py` 中的 Qwen3-ASR 引擎均实现此接口。

### Sherpa-ONNX Paraformer

- 模型：Paraformer-zh（中文）
- 后端：sherpa-onnx，推理延迟极低（RTF ≈ 0.007，比实时快 ~140 倍）
- VAD：内置 Silero VAD，支持分段检测
- 配置：`[asr.sherpa]`

### Qwen3-ASR（OpenVINO INT8）

- 模型：Qwen3-ASR 0.6B / 1.7B，OpenVINO INT8 量化
- 后端：OpenVINO Runtime，CPU 推理（RTF ≈ 0.03–0.33）
- 可选 ForcedAligner：提供词级时间戳对齐能力
- 配置：`[asr.qwen_asr]`

两个引擎可通过 `[package]` 开关独立启用，互不干扰，各自注册不同的 API 路由。

### 句子后处理

ASR 输出的原始句子需要经过后处理才能用于字幕显示：

1. **Cutter** — 根据 `cut_line`（停顿阈值）将长句拆成短句
2. **Combiner** — 根据 `combine_line` 将间隔过短的句子合并

两者互为反向操作，建议只启用其中一个。如果同时启用，需要 `combine_line > cut_line`。

### 数据结构

ASR 结果统一为 `Sentence` 结构（定义在 `types.py`），包含：
- 文本内容
- 词级时间戳（`Word` 列表）
- 起止时间

各引擎的内部输出均会转换为统一的 `Sentence` 格式，供上层逻辑消费。

## 与其他模块的关系

- **api/routes/asr_sherpa.py** 暴露 Sherpa-ONNX HTTP 接口
- **api/routes/asr_qwen.py** 暴露 Qwen3-ASR HTTP 接口
- **api/routes/asr_reload.py** 暴露热重载接口
- **api/logic/sherpa_asr.py** / **api/logic/qwen_asr.py** 封装推理逻辑
- **api/clients/asr_client.py** 提供客户端封装

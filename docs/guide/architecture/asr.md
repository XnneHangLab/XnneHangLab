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
    └── forced_aligner.py # ForcedAligner（词级时间戳对齐，**必须配置**）
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

**为什么保留 Sherpa？**

Sherpa-ONNX Paraformer 在纯中文场景下速度极快。以同一句「那年长街春意正浓，策马同游」为例，Sherpa 仅需约 **0.23s**（CPU），而 Qwen3-ASR-1.7B 同等硬件下约需 2–3s。对于中文实时流场景，这个差距非常显著。

但 Sherpa 存在明确的语言局限性：**不支持英文和日文**——英文会乱码，日文会空返回。因此：

- 纯中文场景 → 优先考虑 Sherpa（速度优先）
- 中英/中日混合或多语言场景 → 必须用 Qwen3-ASR

### Qwen3-ASR（OpenVINO INT8）

- 模型：Qwen3-ASR 0.6B / 1.7B，OpenVINO INT8 量化
- 后端：OpenVINO Runtime，CPU 推理
- ForcedAligner：**必须配置**，提供词级时间戳对齐能力；未配置或路径不存在时启动即报错
- 配置：`[asr.qwen_asr]`

两个引擎可通过 `[package]` 开关独立启用，互不干扰，各自注册不同的 API 路由。

#### OpenVINO 推理延迟与预热

OpenVINO CPU plugin 首次推理时触发 JIT kernel 编译（thread warm-up），之后进入稳定状态。以 i7-12th Gen（2022 年，CPU 散热未清灰）为例：

| 请求 | Qwen3-ASR-1.7B |
|------|----------------|
| 第 1 次（冷启动 JIT） | ~20.7s |
| 第 2 次（已预热） | ~2.9s |
| 第 3 次（已预热） | ~2.2s |

预热完成后，推理延迟稳定在 2–3s（~10s 音频片段）。

**关于重启后的冷启动：** 首次冷启动（JIT 编译）约 20s。启用 `cache_dir` 后，编译结果会持久化到 `{model_dir}/.ov_cache/`，后续重启可跳过 JIT 阶段，冷启动时间显著缩短。

**关于 idle 导致的重新预热（已修复）：** 原实现使用同步 `request.infer()`，OpenVINO CPU thread pool 在约 30s 无请求后会 idle-down，下次推理重新触发预热（表现为突然变慢 10s 以上）。当前实现已改为 `start_async() + wait()` + thread pinning，worker thread 保持 event-wait 状态，**idle 后不再重新预热**，对实时对话场景友好。

#### 长音频 benchmark（example2.m4a，~4m 13s，中英混合）

硬件：i7-12th Gen（2022 笔记本），ForcedAligner 放在 GPU 上跑

| Metric | 数值 |
|--------|------|
| 总耗时 | 68.8s |
| ASR 总计 | 59.3s（28 个 chunk） |
| Aligner 总计 | 6.7s（GPU） |
| 平均每 chunk（~10s 音频） | ~2.5s ASR + ~0.3s align |

典型 chunk 耗时：

```
[226910,236910] dur=10000ms  asr=3.257s  align=0.330s
[236910,246910] dur=10000ms  asr=2.498s  align=0.296s
[246910,253454] dur=6544ms   asr=1.589s  align=0.072s
```

> **0.6B vs 1.7B 速度差**：0.6B 比 1.7B 略快，但差距比直觉上小。原因是 audio encoder（两个模型共享相近架构）的耗时在 per-chunk 中占比较高，decoder 参数量的差异被稀释了。

#### ForcedAligner 放 GPU 的收益

ForcedAligner CPU 推理延迟与 ASR 本身相当，严重拖慢整体速度。放到 GPU（`forced_aligner_device = "cuda"`）后，align 耗时降至 0.07–0.33s，几乎可以忽略不计。

建议：有独显的机器一律把 ForcedAligner 放 GPU。

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

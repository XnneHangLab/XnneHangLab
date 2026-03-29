from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

QwenTTSModelName = Literal["0.6b", "1.7b"]


class QwenTTSSettings(BaseModel):
    model_name: Annotated[
        QwenTTSModelName,
        Field("1.7b", title="Qwen-TTS model name"),
    ]
    model_0_6b_path: Annotated[
        str,
        Field("./models/Qwen3-TTS-12Hz-0.6B-Base", title="Qwen3-TTS 0.6B model path"),
    ]
    model_1_7b_path: Annotated[
        str,
        Field("./models/Qwen3-TTS-12Hz-1.7B-Base", title="Qwen3-TTS 1.7B model path"),
    ]
    device: Annotated[
        str,
        Field("", title="Qwen-TTS device (empty = auto detect)"),
    ]
    warmup_cuda_graphs: Annotated[
        bool,
        Field(True, title="Warm up CUDA graphs after loading Qwen-TTS"),
    ]

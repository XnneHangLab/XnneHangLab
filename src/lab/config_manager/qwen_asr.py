from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

QwenASRModelName = Literal["0.6b", "1.7b"]
QwenASRSettingsTitle = Literal[
    "model_dir",
    "preload_models",
    "model_0_6b_path",
    "model_1_7b_path",
    "device",
    "cpu_threads",
    "forced_aligner_path",
    "forced_aligner_device",
]


class QwenASRSettings(BaseModel):
    model_dir: Annotated[str, Field("./models", title="Qwen3-ASR model directory")]
    preload_models: Annotated[
        list[QwenASRModelName],
        Field(default_factory=lambda: ["0.6b"], title="Preloaded Qwen3-ASR models"),
    ]
    model_0_6b_path: Annotated[
        str,
        Field("./models/Qwen3-ASR-0.6B-INT8-OpenVINO", title="Qwen3-ASR 0.6B OpenVINO model path"),
    ]
    model_1_7b_path: Annotated[
        str,
        Field("./models/Qwen3-ASR-1.7B-INT8-OpenVINO", title="Qwen3-ASR 1.7B OpenVINO model path"),
    ]
    device: Annotated[str, Field("CPU", title="OpenVINO device")]
    cpu_threads: Annotated[int, Field(0, ge=0, title="OpenVINO CPU threads")]
    forced_aligner_path: Annotated[
        str,
        Field("", title="Qwen3-ForcedAligner model path (empty = disabled)"),
    ]
    forced_aligner_device: Annotated[str, Field("cpu", title="ForcedAligner device")]

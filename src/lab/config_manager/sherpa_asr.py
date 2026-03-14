from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

SherpaASRSettingsTitle = Literal["asr_model_dir", "vad_model_path", "num_threads"]


class SherpaASRSettings(BaseModel):
    """sherpa-onnx ASR 引擎配置。"""

    asr_model_dir: Annotated[
        str,
        Field(
            "./models/sherpa-onnx-paraformer-zh-2023-09-14",
            title="paraformer 模型目录",
        ),
    ]
    vad_model_path: Annotated[
        str,
        Field(
            "./models/silero_vad.onnx",
            title="silero-vad 模型路径",
        ),
    ]
    num_threads: Annotated[int, Field(2, ge=1, title="推理线程数")]

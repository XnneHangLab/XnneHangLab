from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

SherpaASRSettingsTitle = Literal[
    "asr_model_dir",
    "num_threads",
    "vad_min_silence_duration",
    "vad_min_speech_duration",
    "vad_max_speech_duration",
]


class SherpaASRSettings(BaseModel):
    asr_model_dir: Annotated[
        str,
        Field(
            "./models/sherpa-onnx-paraformer-zh-2023-09-14",
            title="Paraformer model directory",
        ),
    ]
    num_threads: Annotated[int, Field(2, ge=1, title="Inference threads")]
    vad_min_silence_duration: Annotated[float, Field(0.25, ge=0.0, title="VAD min silence duration")]
    vad_min_speech_duration: Annotated[float, Field(0.25, ge=0.0, title="VAD min speech duration")]
    vad_max_speech_duration: Annotated[float, Field(8.0, gt=0.0, title="VAD max speech duration")]

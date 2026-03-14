from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

QwenASRModelName = Literal["0.6b", "1.7b"]
QwenASRSettingsTitle = Literal[
    "model_dir",
    "preload_models",
    "model_0_6b_path",
    "model_1_7b_path",
    "forced_aligner_path",
    "device",
]


class QwenASRSettings(BaseModel):
    """Qwen3-ASR 引擎配置。

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """

    model_dir: Annotated[str, Field("./models", title="Qwen3-ASR 模型目录")]
    preload_models: Annotated[list[QwenASRModelName], Field(["0.6b"], title="启动时预加载的模型列表")]
    model_0_6b_path: Annotated[str, Field("./models/Qwen3-ASR-0.6B", title="Qwen3-ASR 0.6B 模型路径")]
    model_1_7b_path: Annotated[str, Field("./models/Qwen3-ASR-1.7B", title="Qwen3-ASR 1.7B 模型路径")]
    forced_aligner_path: Annotated[
        str,
        Field("./models/Qwen3-ForcedAligner-0.6B", title="Qwen3 Forced Aligner 模型路径"),
    ]
    device: Annotated[str, Field("cpu", title="推理设备")]

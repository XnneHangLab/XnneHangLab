from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

QwenASRSettingsTitle = Literal["model_id", "device"]


class QwenASRSettings(BaseModel):
    """Qwen3-ASR 引擎配置。"""

    model_id: Annotated[str, Field("Qwen/Qwen3-ASR-0.6B", title="ModelScope 模型 ID")]
    device: Annotated[str, Field("cpu", title="推理设备")]

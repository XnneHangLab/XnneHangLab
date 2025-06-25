from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from pydantic import BaseModel

if TYPE_CHECKING:
    from funasr import AutoModel


# 定义输入模型
class TTSRequest(BaseModel):
    text: str


class ModelInstance(TypedDict):
    asr: AutoModel | None
    vad: AutoModel | None

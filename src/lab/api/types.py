from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    from funasr import AutoModel
    from whisper.model import Whisper


class FunASRModels(TypedDict):
    asr: AutoModel | None
    vad: AutoModel | None
    asr_no_punc: AutoModel | None


class GlobalModelContainer(TypedDict):
    funasr: FunASRModels | None
    whisper: Whisper | None


class GPTSoVITSResponse(TypedDict):
    audio_type: Literal["mp3"]
    audio_rate: int
    audio_byte: bytes  # base64.b64encode(opus_bytes).decode("utf-8")


class DeepLXResponse(TypedDict):
    source_text: str  # 源文本
    target_text: str  # 目标文本

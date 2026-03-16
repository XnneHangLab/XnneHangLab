from __future__ import annotations

from typing import Literal, TypedDict


class GPTSoVITSResponse(TypedDict):
    audio_type: Literal["mp3"]
    audio_rate: int
    audio_byte: bytes


class DeepLXResponse(TypedDict):
    source_text: str
    target_text: str


class LLMTranslateResponse(TypedDict):
    source_text: str
    target_text: str

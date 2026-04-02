from __future__ import annotations

from typing import Literal, TypedDict


class QwenTTSResponse(TypedDict):
    audio_type: Literal["wav"]
    audio_rate: int
    audio_byte: bytes


class GSVLiteResponse(TypedDict):
    audio_type: Literal["wav"]
    audio_rate: int
    audio_byte: bytes


class GenieTTSResponse(TypedDict):
    audio_type: Literal["wav"]
    audio_rate: int
    audio_byte: bytes


class DeepLXResponse(TypedDict):
    source_text: str
    target_text: str


class LLMTranslateResponse(TypedDict):
    source_text: str
    target_text: str

from __future__ import annotations

from typing_extensions import TypedDict


class ASRResponse(TypedDict):
    """字级或词级 ASR 响应。"""

    key: str
    text: str
    timestamp: list[list[int]]


class VadResponse(TypedDict):
    """VAD 响应。"""

    key: str
    timestamp: list[list[int]]
    audio_length: int


class SenseVoiceResponse(TypedDict):
    """SenseVoice 风格 ASR 响应。"""

    key: str
    status: str
    text: str
    timestamp: list[list[int]]


class Word(TypedDict):
    """句子中的单个词或字符。"""

    text: str
    start: int
    end: int


class Sentence(TypedDict):
    """经过切句后的字幕句子。"""

    text: str
    start: int
    end: int
    Words: list[Word]


class CutPoint(TypedDict):
    """字幕切分点。"""

    sentence_index: int
    word_index: int


class DebugMessage(TypedDict):
    """调试信息。"""

    segmented_text: list[str]
    total_words_num: int
    total_ts_num: int

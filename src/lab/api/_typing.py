from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from funasr import AutoModel


class ModelInstance(TypedDict):
    asr: AutoModel | None
    vad: AutoModel | None
    asr_no_punc: AutoModel | None

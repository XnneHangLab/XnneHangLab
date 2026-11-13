from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ImageSource = Literal["tool", "upload"]
DEFAULT_TOOL_IMAGE_LABEL = "tool1"


@dataclass(frozen=True)
class ImagePayload:
    """An in-memory image with a stable label for chat input."""

    label: str
    b64: str
    mime: str
    source: ImageSource

from __future__ import annotations

import os
from typing import Annotated

from pydantic import BaseModel, Field


class TTSPreprocessorConfig(BaseModel):
    """Internal TTS text preprocessing settings used by VTuber flows."""

    remove_special_char: Annotated[bool, Field(True)]
    ignore_brackets: Annotated[bool, Field(True)]
    ignore_parentheses: Annotated[bool, Field(True)]
    ignore_asterisks: Annotated[bool, Field(True)]
    ignore_angle_brackets: Annotated[bool, Field(True)]


class CharacterSettings(BaseModel):
    """Internal character identity used after profile loading."""

    conf_name: Annotated[str, Field("elaina-local")]
    conf_uid: Annotated[str, Field("elaina-local-001")]
    live2d_model_name: Annotated[str, Field("Elaina")]
    character_name: Annotated[str, Field("Elaina")]
    avatar: Annotated[str, Field("ico_lss.png")]
    human_name: Annotated[str, Field("Human")]
    tts_preprocessor_config: Annotated[TTSPreprocessorConfig, Field(TTSPreprocessorConfig())]  # pyright: ignore[reportCallIssue]


class VtuberSettings(BaseModel):
    """Legacy placeholder kept for module compatibility."""


def scan_bg_directory() -> list[str]:
    """Scan the available background directory and return image file names."""

    bg_files: list[str] = []
    bg_dir = "static/backgrounds"
    for _, _, files in os.walk(bg_dir):
        for file in files:
            if file.endswith((".jpg", ".jpeg", ".png", ".gif")):
                bg_files.append(file)
    return bg_files

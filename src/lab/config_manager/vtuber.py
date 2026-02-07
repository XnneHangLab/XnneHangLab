from __future__ import annotations

import os
from typing import Annotated

from pydantic import BaseModel, Field


class TTSPreprocessorConfig(BaseModel):
    """TTS 文本预处理配置。"""

    remove_special_char: Annotated[bool, Field(True)]
    ignore_brackets: Annotated[bool, Field(True)]
    ignore_parentheses: Annotated[bool, Field(True)]
    ignore_asterisks: Annotated[bool, Field(True)]
    ignore_angle_brackets: Annotated[bool, Field(True)]


class CharacterSettings(BaseModel):
    """VTuber 角色配置。

    包含角色身份标识、Live2D 模型名、显示名称与头像，以及 TTS 文本预处理策略。
    """

    conf_name: Annotated[str, Field("elaina-local")]
    conf_uid: Annotated[str, Field("elaina-local-001")]
    live2d_model_name: Annotated[str, Field("Elaina")]
    character_name: Annotated[str, Field("Elaina")]
    avatar: Annotated[str, Field("ico_lss.png")]
    human_name: Annotated[str, Field("Human")]
    tts_preprocessor_config: Annotated[TTSPreprocessorConfig, Field(TTSPreprocessorConfig())]  # pyright: ignore[reportCallIssue]


class VtuberSettings(BaseModel):
    """VTuber 模块配置入口。"""

    character_config: Annotated[CharacterSettings, Field(CharacterSettings())]  # pyright: ignore[reportCallIssue]


class TranslatorConfig(BaseModel):
    """兼容旧接口，当前翻译配置由 agent 侧管理。"""


def scan_bg_directory() -> list[str]:
    """扫描可用背景图目录并返回图片文件名列表。"""

    bg_files: list[str] = []
    bg_dir = "static/backgrounds"
    for _, _, files in os.walk(bg_dir):
        for file in files:
            if file.endswith((".jpg", ".jpeg", ".png", ".gif")):
                bg_files.append(file)
    return bg_files

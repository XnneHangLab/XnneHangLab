# 这里是本项目自己的配置管理器， 而下面的子项目比如 vtuber, 则是 open-llm-vtuber 的。
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from lab.streamlit.i18n import Device

from .abs_root import RootAbsDir
from .agent import AgentSettings, LLM_Provider
from .asr import ASRSettings, FunASRSettings, WhisperSettings
from .audio_recognize import AudioRecognizeSettings
from .config import XnneHangLabSettings, get_setting_title, load_settings_file, write_settings_file
from .mcp import ToolContextConfig
from .package import PackagesSettings


class LLMSetting(BaseModel):
    llm_base_url: Annotated[str, Field("", title="LLM Base URL")]
    llm_api_key: Annotated[str, Field("", title="LLM API Key")]


__all__ = [
    "RootAbsDir",
    "AudioRecognizeSettings",
    "FunASRSettings",
    "load_settings_file",
    "write_settings_file",
    "get_setting_title",
    "Device",
    "AgentSettings",
    "LLM_Provider",
    "PackagesSettings",
    "XnneHangLabSettings",
    "WhisperSettings",
    "ASRSettings",
    "LLMSetting",
    "ToolContextConfig",
]

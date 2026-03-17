from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from lab.streamlit.i18n import Device

from .abs_root import RootAbsDir
from .agent import AgentSettings, LLM_Provider, TranslateProvider
from .asr import ASRSettings
from .audio_recognize import AudioRecognizeSettings
from .config import XnneHangLabSettings, get_setting_title, load_settings_file, write_settings_file
from .embedding import LocalEmbeddingSetting
from .package import PackagesSettings
from .qwen_asr import QwenASRSettings
from .sherpa_asr import SherpaASRSettings


class LLMSetting(BaseModel):
    llm_base_url: Annotated[str, Field("", title="LLM Base URL")]
    llm_api_key: Annotated[str, Field("", title="LLM API Key")]


__all__ = [
    "RootAbsDir",
    "AudioRecognizeSettings",
    "SherpaASRSettings",
    "QwenASRSettings",
    "load_settings_file",
    "write_settings_file",
    "get_setting_title",
    "Device",
    "AgentSettings",
    "LLM_Provider",
    "TranslateProvider",
    "PackagesSettings",
    "LocalEmbeddingSetting",
    "XnneHangLabSettings",
    "ASRSettings",
    "LLMSetting",
]

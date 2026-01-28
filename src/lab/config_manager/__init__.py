# 这里是本项目自己的配置管理器， 而下面的子项目比如 vtuber, 则是 open-llm-vtuber 的。
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from .abs_root import RootAbsDir
from .agent import AgentSettings, LLM_Provider
from .asr import ASRSettings, Device, FunASRSettings, WhisperSettings
from .audio_recognize import AudioRecognizeSettings
from .config import XnneHangLabSettings, get_setting_title, load_settings_file, write_settings_file
from .package import PackagesSettings


class LLMSetting(BaseModel):
    llm_base_url: Annotated[str, Field("", title="LLM Base URL")]
    llm_api_key: Annotated[str, Field("", title="LLM API Key")]


def resolve_provider(lab_settings: XnneHangLabSettings, provider: LLM_Provider) -> LLMSetting:
    """
    Resolve the LLM provider to its base URL and API key.
    根据 provider 来返回对应的 LLMBaseSetting。这个函数 Tool Model 和 Chat Model 初始化都会用到，所以放在这里。
    """
    if provider == "openai":
        return LLMSetting(
            llm_base_url=lab_settings.agent.llm.openai.llm_base_url,
            llm_api_key=lab_settings.agent.llm.openai.llm_api_key,
        )
    elif provider == "lingyi":
        return LLMSetting(
            llm_base_url=lab_settings.agent.llm.lingyi.llm_base_url,
            llm_api_key=lab_settings.agent.llm.lingyi.llm_api_key,
        )
    elif provider == "gemini":
        return LLMSetting(
            llm_base_url=lab_settings.agent.llm.gemini.llm_base_url,
            llm_api_key=lab_settings.agent.llm.gemini.llm_api_key,
        )
    elif provider == "oaipro":
        return LLMSetting(
            llm_base_url=lab_settings.agent.llm.oaipro.llm_base_url,
            llm_api_key=lab_settings.agent.llm.oaipro.llm_api_key,
        )
    elif provider == "cerebras":
        return LLMSetting(
            llm_base_url=lab_settings.agent.llm.cerebras.llm_base_url,
            llm_api_key=lab_settings.agent.llm.cerebras.llm_api_key,
        )


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
    "resolve_provider",
]

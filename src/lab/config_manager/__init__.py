# 这里是本项目自己的配置管理器， 而下面的子项目比如 vtuber, 则是 open-llm-vtuber 的。
from __future__ import annotations

from .abs_root import RootAbsDir
from .agent import AgentSettings
from .audio_recognize import AudioRecognizeSettings
from .config import XnneHangLabSettings, get_setting_title, load_settings_file, write_settings_file
from .funasr import Device, FunASRSettings
from .package import PackagesSettings

__all__ = [
    "RootAbsDir",
    "AudioRecognizeSettings",
    "FunASRSettings",
    "load_settings_file",
    "write_settings_file",
    "get_setting_title",
    "Device",
    "AgentSettings",
    "PackagesSettings",
    "XnneHangLabSettings",
]

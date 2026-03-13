from __future__ import annotations

import os
import platform

# if sys.version_info >= (3, 11):
import tomllib  # Python 3.11+ 自带
from pathlib import Path
from typing import Annotated, Any, overload

import tomli_w as tomlw  # 安装 tomli_w 用于写入
from pydantic import BaseModel, Field

from lab.config_manager.abs_root import RootAbsDir
from lab.config_manager.agent import AgentSettings
from lab.config_manager.asr import (
    ASRSettings,
    ASRSettingsTitle,
    FunASRSettings,
    FunASRSettingsTitle,
    WhisperSettings,
    WhisperSettingsTitle,
)
from lab.config_manager.audio_recognize import AudioRecognizeSettings, AudioRecognizeSettingsTitle
from lab.config_manager.mcp import MCPSettings
from lab.config_manager.memory_bench import MemoryBenchSettings
from lab.config_manager.package import PackagesSettings
from lab.config_manager.server import ServerSettings
from lab.config_manager.vtuber import VtuberSettings

toml_loads = tomllib.loads
toml_dumps = tomlw.dumps  # 使用 tomlw.dumps


def xdg_config_home() -> Path:
    if (env := os.environ.get("XDG_CONFIG_HOME")) and (path := Path(env)).is_absolute():
        return path
    home = Path.home()
    if platform.system() == "Windows":
        return home / "AppData"
    return home / ".config"


def search_for_settings_file(setting_name: str) -> Path | None:
    config_dir = Path("config")
    settings_file = config_dir / setting_name
    if not settings_file.exists():  # 当前目录没找到
        settings_file = xdg_config_home() / setting_name
    if not settings_file.exists():  # XDG_CONFIG_HOME 也没找到
        return None
    return settings_file


@overload
def load_settings_file(setting_name: str, setting: type[VtuberSettings]) -> VtuberSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[FunASRSettings]) -> FunASRSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[WhisperSettings]) -> WhisperSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[AudioRecognizeSettings]) -> AudioRecognizeSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[RootAbsDir]) -> RootAbsDir: ...


@overload
def load_settings_file(setting_name: str, setting: type[AgentSettings]) -> AgentSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[PackagesSettings]) -> PackagesSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[XnneHangLabSettings]) -> XnneHangLabSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[MCPSettings]) -> MCPSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[ASRSettings]) -> ASRSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[ServerSettings]) -> ServerSettings: ...


class XnneHangLabSettings(BaseModel):
    conf_version: Annotated[str, Field("v1.5.0", title="配置版本")]
    asr: Annotated[ASRSettings, Field(ASRSettings())]  # pyright: ignore[reportCallIssue]
    webui: Annotated[AudioRecognizeSettings, Field(AudioRecognizeSettings())]  # pyright: ignore[reportCallIssue]
    agent: Annotated[AgentSettings, Field(AgentSettings())]  # pyright: ignore[reportCallIssue]
    mcp: Annotated[MCPSettings, Field(MCPSettings())]  # pyright: ignore[reportCallIssue]
    package: Annotated[PackagesSettings, Field(PackagesSettings())]  # pyright: ignore[reportCallIssue]
    root: Annotated[RootAbsDir, Field(RootAbsDir())]  # pyright: ignore[reportCallIssue]
    server: Annotated[ServerSettings, Field(ServerSettings())]  # pyright: ignore[reportCallIssue]
    vtuber: Annotated[VtuberSettings, Field(VtuberSettings())]  # pyright: ignore[reportCallIssue]
    memory_bench: Annotated[MemoryBenchSettings, Field(MemoryBenchSettings())]  # pyright: ignore[reportCallIssue]


def load_settings_file(
    setting_name: str,
    setting: (
        type[
            FunASRSettings
            | WhisperSettings
            | AudioRecognizeSettings
            | RootAbsDir
            | AgentSettings
            | PackagesSettings
            | XnneHangLabSettings
            | MCPSettings
            | ASRSettings
            | ServerSettings
            | VtuberSettings
        ]
    ),
) -> (
    FunASRSettings
    | WhisperSettings
    | AudioRecognizeSettings
    | RootAbsDir
    | AgentSettings
    | PackagesSettings
    | XnneHangLabSettings
    | MCPSettings
    | ASRSettings
    | ServerSettings
    | VtuberSettings
):
    """加载配置文件，如果不存在则创建默认配置文件在当前工作目录。"""
    settings_file = search_for_settings_file(setting_name=setting_name)
    if settings_file is None:
        config_dir = Path("config")
        if not config_dir.exists():
            config_dir.mkdir()
        settings_file = config_dir / setting_name
        print(f"未找到配置文件，将初始化默认配置:{str(settings_file)}")
        settings_file.touch()
    with settings_file.open("r", encoding="utf-8") as f:
        settings_raw: Any = tomllib.loads(f.read())
    validated_settings = setting.model_validate(settings_raw)
    write_settings_file(settings_name=setting_name, settings=validated_settings)
    return validated_settings


def write_settings_file(
    settings_name: str,
    settings: FunASRSettings
    | WhisperSettings
    | AudioRecognizeSettings
    | RootAbsDir
    | AgentSettings
    | PackagesSettings
    | XnneHangLabSettings
    | MCPSettings
    | ASRSettings
    | ServerSettings
    | VtuberSettings,
) -> None:
    """将 Setting 对象写入 TOML 文件。"""
    settings_file = search_for_settings_file(setting_name=settings_name)
    if settings_file is None:
        settings_file = Path("config") / settings_name
        settings_file.touch()
    try:
        with settings_file.open("w", encoding="utf-8") as f:
            toml_string = toml_dumps(settings.model_dump(exclude_none=True))  # type: ignore
            f.write(toml_string)
    except Exception as e:
        print(f"写入配置文件失败: {e}")


@overload
def get_setting_title(
    name: FunASRSettingsTitle,
    setting: type[FunASRSettings],
) -> str:
    return str(setting.model_fields[name].field_info.title)  # type: ignore


@overload
def get_setting_title(
    name: AudioRecognizeSettingsTitle,
    setting: type[AudioRecognizeSettings],
) -> str:
    return str(setting.model_fields[name].field_info.title)  # type: ignore


@overload
def get_setting_title(
    name: WhisperSettingsTitle,
    setting: type[WhisperSettings],
) -> str:
    return str(setting.model_fields[name].field_info.title)  # type: ignore


@overload
def get_setting_title(
    name: ASRSettingsTitle,
    setting: type[ASRSettings],
) -> str:
    return str(setting.model_fields[name].field_info.title)  # type: ignore


def get_setting_title(
    name: FunASRSettingsTitle | AudioRecognizeSettingsTitle | WhisperSettingsTitle | ASRSettingsTitle,
    setting: type[FunASRSettings | AudioRecognizeSettings | WhisperSettings | ASRSettings],
) -> str:
    """获取配置项(英文)的标题。（中文）

    guide -> 指引,
    output_type -> 输出类型,
    subtitle_speed -> 字幕速度,
    ...
    """
    return str(setting.model_fields[name].title)

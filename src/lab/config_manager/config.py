from __future__ import annotations

import os
import platform
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, overload

import tomli_w as tomlw
from pydantic import BaseModel, Field

from lab.config_manager.abs_root import RootAbsDir
from lab.config_manager.agent import AgentSettings
from lab.config_manager.asr import ASRSettings, ASRSettingsTitle
from lab.config_manager.audio_recognize import AudioRecognizeSettings, AudioRecognizeSettingsTitle
from lab.config_manager.memory_bench import MemoryBenchSettings
from lab.config_manager.package import PackagesSettings
from lab.config_manager.server import ServerSettings
from lab.config_manager.vtuber import VtuberSettings

toml_dumps = tomlw.dumps

if TYPE_CHECKING:
    from lab.config_manager.qwen_asr import QwenASRSettings, QwenASRSettingsTitle
    from lab.config_manager.sherpa_asr import SherpaASRSettings, SherpaASRSettingsTitle


def xdg_config_home() -> Path:
    """返回当前平台下的配置目录。

    Args:
        None.

    Returns:
        Path: 当前平台的配置目录路径。

    Raises:
        None.
    """
    if (env := os.environ.get("XDG_CONFIG_HOME")) and (path := Path(env)).is_absolute():
        return path

    home = Path.home()
    if platform.system() == "Windows":
        return home / "AppData"
    return home / ".config"


def search_for_settings_file(setting_name: str) -> Path | None:
    """查找配置文件路径。

    Args:
        setting_name: 配置文件名。

    Returns:
        Path | None: 找到时返回配置文件路径，否则返回 None。

    Raises:
        None.
    """
    config_dir = Path("config")
    settings_file = config_dir / setting_name
    if not settings_file.exists():
        settings_file = xdg_config_home() / setting_name
    if not settings_file.exists():
        return None
    return settings_file


@overload
def load_settings_file(setting_name: str, setting: type[VtuberSettings]) -> VtuberSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[SherpaASRSettings]) -> SherpaASRSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[QwenASRSettings]) -> QwenASRSettings: ...


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
def load_settings_file(setting_name: str, setting: type[ASRSettings]) -> ASRSettings: ...


@overload
def load_settings_file(setting_name: str, setting: type[ServerSettings]) -> ServerSettings: ...


class XnneHangLabSettings(BaseModel):
    conf_version: Annotated[str, Field("v1.5.1", title="配置版本")]
    asr: Annotated[ASRSettings, Field(ASRSettings())]  # pyright: ignore[reportCallIssue]
    webui: Annotated[AudioRecognizeSettings, Field(AudioRecognizeSettings())]  # pyright: ignore[reportCallIssue]
    agent: Annotated[AgentSettings, Field(AgentSettings())]  # pyright: ignore[reportCallIssue]
    package: Annotated[PackagesSettings, Field(PackagesSettings())]  # pyright: ignore[reportCallIssue]
    root: Annotated[RootAbsDir, Field(RootAbsDir())]  # pyright: ignore[reportCallIssue]
    server: Annotated[ServerSettings, Field(ServerSettings())]  # pyright: ignore[reportCallIssue]
    vtuber: Annotated[VtuberSettings, Field(VtuberSettings())]  # pyright: ignore[reportCallIssue]
    memory_bench: Annotated[MemoryBenchSettings, Field(MemoryBenchSettings())]  # pyright: ignore[reportCallIssue]


def load_settings_file(
    setting_name: str,
    setting: type[
        SherpaASRSettings
        | QwenASRSettings
        | AudioRecognizeSettings
        | RootAbsDir
        | AgentSettings
        | PackagesSettings
        | XnneHangLabSettings
        | ASRSettings
        | ServerSettings
        | VtuberSettings
    ],
) -> (
    SherpaASRSettings
    | QwenASRSettings
    | AudioRecognizeSettings
    | RootAbsDir
    | AgentSettings
    | PackagesSettings
    | XnneHangLabSettings
    | ASRSettings
    | ServerSettings
    | VtuberSettings
):
    """加载配置文件，不存在时写入默认配置。

    Args:
        setting_name: 配置文件名。
        setting: 目标配置模型类型。

    Returns:
        配置模型实例。

    Raises:
        None.
    """
    settings_file = search_for_settings_file(setting_name=setting_name)
    if settings_file is None:
        config_dir = Path("config")
        config_dir.mkdir(exist_ok=True)
        settings_file = config_dir / setting_name
        settings_file.touch()

    with settings_file.open("r", encoding="utf-8") as file:
        settings_raw: Any = tomllib.loads(file.read())

    validated_settings = setting.model_validate(settings_raw)
    write_settings_file(settings_name=setting_name, settings=validated_settings)
    return validated_settings


def write_settings_file(
    settings_name: str,
    settings: SherpaASRSettings
    | QwenASRSettings
    | AudioRecognizeSettings
    | RootAbsDir
    | AgentSettings
    | PackagesSettings
    | XnneHangLabSettings
    | ASRSettings
    | ServerSettings
    | VtuberSettings,
) -> None:
    """将配置对象写入 TOML 文件。

    Args:
        settings_name: 配置文件名。
        settings: 待写入的配置模型。

    Returns:
        None.

    Raises:
        None.
    """
    settings_file = search_for_settings_file(setting_name=settings_name)
    if settings_file is None:
        settings_file = Path("config") / settings_name
        settings_file.touch()

    with settings_file.open("w", encoding="utf-8") as file:
        file.write(toml_dumps(settings.model_dump(exclude_none=True)))  # type: ignore[arg-type]


@overload
def get_setting_title(name: SherpaASRSettingsTitle, setting: type[SherpaASRSettings]) -> str: ...


@overload
def get_setting_title(name: QwenASRSettingsTitle, setting: type[QwenASRSettings]) -> str: ...


@overload
def get_setting_title(name: AudioRecognizeSettingsTitle, setting: type[AudioRecognizeSettings]) -> str: ...


@overload
def get_setting_title(name: ASRSettingsTitle, setting: type[ASRSettings]) -> str: ...


def get_setting_title(
    name: SherpaASRSettingsTitle | QwenASRSettingsTitle | AudioRecognizeSettingsTitle | ASRSettingsTitle,
    setting: type[SherpaASRSettings | QwenASRSettings | AudioRecognizeSettings | ASRSettings],
) -> str:
    """读取配置项的展示标题。

    Args:
        name: 配置字段名。
        setting: 配置模型类型。

    Returns:
        str: 字段标题。

    Raises:
        KeyError: 字段不存在时抛出。
    """
    return str(setting.model_fields[name].title)

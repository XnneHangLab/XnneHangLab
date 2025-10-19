from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from lab.config_manager.webui_i18n_model import Guide, SubtitleSpeed, WebUIi18nSettings

# 开放的配置项
AudioRecognizeSettingsTitle = Literal[
    "guide",
    "subtitle_speed",
]
# 下拉式配置项
AudioRecognizeDropdownSetting = Literal["guide", "subtitle_speed"]


class AudioRecognizeSettings(WebUIi18nSettings):
    guide: Annotated[Guide, Field("open", title="指引")]
    subtitle_speed: Annotated[SubtitleSpeed, Field("normal", title="字幕速度")]

    # 集中映射避免重复 if-elif-else
    _FIELD_TO_LITERAL = {
        "guide": Guide,
        "subtitle_speed": SubtitleSpeed,
    }


def main():
    from lab.config_manager.config import (
        XnneHangLabSettings,
        load_settings_file,
        search_for_settings_file,
        write_settings_file,
    )

    config_path = search_for_settings_file("audio_recognize.toml")
    if config_path is not None and config_path.exists():
        config_path.unlink()  # ensure load default
    audio_recognize_settings = load_settings_file("audio_recognize.toml", AudioRecognizeSettings)
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    lab_settings.webui = audio_recognize_settings
    write_settings_file("lab.toml", lab_settings)
    config_path = search_for_settings_file("audio_recognize.toml")
    if config_path is not None and config_path.exists():
        config_path.unlink()  # remove audio_recognize.toml

from __future__ import annotations

from typing import Annotated, Literal, get_args

from pydantic import BaseModel, Field

from lab._dictionary import audio_setting_dictionary

# 开放的配置项
AudioRecognizeSettingsTitle = Literal["guide", "output_type", "subtitle_speed"]
AudioRecognizeGuide = Literal["open", "close"]
AudioRecognizeOutputType = Literal["with_timestamp", "without_timestamp"]
AudioRecognizeSubtitleSpeed = Literal["slow", "normal", "fast"]


class AudioRecognizeSettings(BaseModel):
    guide: Annotated[AudioRecognizeGuide, Field("open", title="指引")]
    output_type: Annotated[
        AudioRecognizeOutputType,
        Field("with_timestamp", title="输出类型"),
    ]
    subtitle_speed: Annotated[AudioRecognizeSubtitleSpeed, Field("normal", title="字幕速度")]

    def get_zh_option_list(self, key: AudioRecognizeSettingsTitle):
        """获取中文配置项列表"""
        if key == "guide":
            return [audio_setting_dictionary[x][1] for x in get_args(AudioRecognizeGuide)]
        elif key == "output_type":
            return [audio_setting_dictionary[x][1] for x in get_args(AudioRecognizeOutputType)]
        elif key == "subtitle_speed":
            return [audio_setting_dictionary[x][1] for x in get_args(AudioRecognizeSubtitleSpeed)]
        else:
            raise ValueError(f"不支持的配置项: {key}")

    def get_index(self, key: AudioRecognizeSettingsTitle):
        """获取配置项的索引"""
        if key == "guide":
            return get_args(AudioRecognizeGuide).index(self.guide)
        elif key == "output_type":
            return get_args(AudioRecognizeOutputType).index(self.output_type)
        elif key == "subtitle_speed":
            return get_args(AudioRecognizeSubtitleSpeed).index(self.subtitle_speed)
        else:
            raise ValueError(f"不支持的配置项: {key}")

    def zh_set_value(self, key: AudioRecognizeSettingsTitle, value: str):
        """通过中文设置配置项"""
        if key == "guide":
            self.guide = get_args(AudioRecognizeGuide)[
                [audio_setting_dictionary[x][1] for x in get_args(AudioRecognizeGuide)].index(value)
            ]
        elif key == "output_type":
            self.output_type = get_args(AudioRecognizeOutputType)[
                [audio_setting_dictionary[x][1] for x in get_args(AudioRecognizeOutputType)].index(value)
            ]


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

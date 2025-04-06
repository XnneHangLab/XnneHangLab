from __future__ import annotations

from typing import Annotated, Literal, get_args

from pydantic import BaseModel, Field

from lab._dictionary import audio_setting_dictionary


class RootAbsDir(BaseModel):
    root_dir: Annotated[str, Field("", title="项目根目录")]  # 项目根目录, 实时计算绝对目录。


# 并不是所有的配置项目都向用户开放。有 title 的是开放项。

Device = Literal["cpu", "cuda"]
# 开放的配置项
RunnerSettingsTitle = Literal[
    "batch_size_s",
    "device",
    "cache_dir",
    "hot_words_path",
    "FFMPEG_PATH",
    "base_model",
    "vad_model",
    "punc_model",
    "custom_output_dir",
    "output_dir",
    "combine_line",
    "cut_line",
    "max_sentence_length",
]


class RunnerSettings(BaseModel):
    batch_size_s: Annotated[int, Field(300, title="批处理大小(默认300,只要能吃满显卡或者CPU即可)")]
    device: Annotated[Literal["cpu", "cuda"], Field("cpu", title="设备选择")]
    punctuation_list: Annotated[str, Field("，。；、？！,.;?!")]
    custom_output_dir: Annotated[bool, Field(False, title="自定义输出目录")]

    cache_dir: Annotated[str, Field("./cache", title="缓存路径")]
    output_dir: Annotated[str, Field("./output", title="输出路径")]
    hot_words_path: Annotated[str, Field("./hot_words.txt", title="热词路径")]
    FFMPEG_PATH: Annotated[str, Field("ffmpeg", title="FFMPEG路径,默认用系统环境变量")]
    base_model: Annotated[
        str,
        Field(
            "./models/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            title="base 模型",
        ),
    ]
    vad_model: Annotated[
        str,
        Field("./models/speech_fsmn_vad_zh-cn-16k-common-pytorch", title="vad 模型"),
    ]
    punc_model: Annotated[
        str,
        Field(
            "./models/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
            title="punc 模型",
        ),
    ]
    sense_voice_model: Annotated[
        str,
        Field(
            "./models/SenseVoiceSmall",
            title="sense_voice 模型",
        ),
    ]

    cut: Annotated[bool, Field(False)]
    cut_line: Annotated[int, Field(400, title="分割间隔(毫秒)")]
    combine: Annotated[bool, Field(False)]
    combine_line: Annotated[int, Field(400, title="合并间隔(毫秒)")]
    max_sentence_length: Annotated[int, Field(20, title="最大单句长度")]
    need_punc: Annotated[bool, Field(False)]

    def get_option_list(self, key: RunnerSettingsTitle):
        if key == "device":
            return list(get_args(Device))
        else:
            raise ValueError(f"不支持的配置项: {key}")

    def get_zh_option_list(self, key: RunnerSettingsTitle):
        if key == "device":
            return [audio_setting_dictionary[x][1] for x in get_args(Device)]
        else:
            raise ValueError(f"不支持的配置项: {key}")

    def get_index(self, key: RunnerSettingsTitle):
        if key == "device":
            return get_args(Device).index(self.device)
        else:
            raise ValueError(f"不支持的配置项: {key}")

    def zh_set_value(self, key: RunnerSettingsTitle, value: str):
        if key == "device":
            self.device = get_args(Device)[[audio_setting_dictionary[x][1] for x in get_args(Device)].index(value)]
        else:
            raise ValueError(f"不支持的配置项: {key}")


# 开放的配置项
AudioSettingsTitle = Literal["guide", "output_type", "subtitle_speed"]
AudioGuide = Literal["open", "close"]
AudioOutputType = Literal["with_timestamp", "without_timestamp"]
AudioSubtitleSpeed = Literal["slow", "normal", "fast"]


class AudioSettings(BaseModel):
    guide: Annotated[AudioGuide, Field("open", title="指引")]
    output_type: Annotated[
        AudioOutputType,
        Field("with_timestamp", title="输出类型"),
    ]
    subtitle_speed: Annotated[AudioSubtitleSpeed, Field("normal", title="字幕速度")]

    def get_zh_option_list(self, key: AudioSettingsTitle):
        """获取中文配置项列表"""
        if key == "guide":
            return [audio_setting_dictionary[x][1] for x in get_args(AudioGuide)]
        elif key == "output_type":
            return [audio_setting_dictionary[x][1] for x in get_args(AudioOutputType)]
        elif key == "subtitle_speed":
            return [audio_setting_dictionary[x][1] for x in get_args(AudioSubtitleSpeed)]
        else:
            raise ValueError(f"不支持的配置项: {key}")

    def get_index(self, key: AudioSettingsTitle):
        """获取配置项的索引"""
        if key == "guide":
            return get_args(AudioGuide).index(self.guide)
        elif key == "output_type":
            return get_args(AudioOutputType).index(self.output_type)
        elif key == "subtitle_speed":
            return get_args(AudioSubtitleSpeed).index(self.subtitle_speed)
        else:
            raise ValueError(f"不支持的配置项: {key}")

    def zh_set_value(self, key: AudioSettingsTitle, value: str):
        """通过中文设置配置项"""
        if key == "guide":
            self.guide = get_args(AudioGuide)[
                [audio_setting_dictionary[x][1] for x in get_args(AudioGuide)].index(value)
            ]
        elif key == "output_type":
            self.output_type = get_args(AudioOutputType)[
                [audio_setting_dictionary[x][1] for x in get_args(AudioOutputType)].index(value)
            ]

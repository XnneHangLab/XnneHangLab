from pydantic import BaseModel, Field
from typing import Annotated, Literal

# 并不是所有的配置项目都向用户开放。有 title 的是开放项。


class RunnerSettings(BaseModel):
    batch_size_s: Annotated[
        int, Field(300, title="批处理大小(默认300,只要能吃满显卡或者CPU即可)")
    ]
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

    cut: Annotated[bool, Field(False)]
    cut_line: Annotated[int, Field(10)]
    combine: Annotated[bool, Field(False)]
    combine_line: Annotated[int, Field(10)]
    max_sentence_length: Annotated[int, Field(20)]
    need_punc: Annotated[bool, Field(False)]


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
]


class AudioSettings(BaseModel):
    guide: Annotated[bool, Field(True, title="指引")]
    output_type: Annotated[
        Literal["with_timestamp", "without_timestamp"],
        Field("with_timestamp", title="输出类型"),
    ]
    subtitle_speed: Annotated[
        Literal["slow", "normal", "fast"], Field("normal", title="字幕速度")
    ]


# 开放的配置项
AudioSettingsTitle = Literal["guide", "output_type", "subtitle_speed"]


class VideoSettings(BaseModel):
    guide: Annotated[bool, Field(True)]
    subtitle_speed: Annotated[Literal["slow", "normal", "fast"], Field("normal")]


# 开放的配置项
VideoSettingsTitle = Literal["guide", "subtitle_speed"]

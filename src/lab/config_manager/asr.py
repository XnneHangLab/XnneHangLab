from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from lab.config_manager.webui_i18n_model import Device, WebUIi18nSettings

# 并不是所有的配置项目都向用户开放。有 title 的是开放项。
# 开放的配置项
FunASRSettingsTitle = Literal[
    "batch_size_s",
    "hot_words_path",
    "base_model",
    "vad_model",
    "punc_model",
    "combine_line",
    "cut_line",
    "max_sentence_length",
]


class FunASRSettings(WebUIi18nSettings):
    batch_size_s: Annotated[int, Field(300, title="批处理大小(默认300,只要能吃满显卡或者CPU即可)")]
    punctuation_list: Annotated[str, Field("，。；、？！,.;?!")]
    hot_words_path: Annotated[str, Field("./hot_words.txt", title="热词路径")]
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

    _FIELD_TO_LITERAL = {
        "device": Device,
    }


# ====== Whisper
# 开放的配置项
WhisperSettingsTitle = Literal["whisper_models_base_dir", "whisper_model_size"]
# 下拉式配置项
WhisperDropDownSetting = Literal["whisper_model_size"]
WhisperModelSize = Literal["tiny", "large-v3-turbo"]


class WhisperSettings(WebUIi18nSettings):
    whisper_models_base_dir: Annotated[str, Field("./models/whisper/", title="Whisper 模型存放列表目录")]
    whisper_model_size: Annotated[str, Field("large-v3-turbo", title="Whisper 模型规格")]

    _FIELD_TO_LITERAL = {
        "whisper_model_size": WhisperModelSize,
    }


# ====== ASR 总配置
# 开放的配置项
ASRSettingsTitle = Literal[
    "device", "custom_output_dir", "cache_dir", "output_dir", "asr_model_provider", "FFMPEG_PATH"
]
# 下拉式配置项
ASRDropdownSetting = Literal["device", "asr_model_provider"]
ASRModelProvider = Literal["funasr", "whisper"]


class ASRSettings(WebUIi18nSettings):
    FFMPEG_PATH: Annotated[str, Field("ffmpeg", title="FFMPEG路径,默认用系统环境变量")]
    device: Annotated[Literal["cpu", "cuda"], Field("cpu", title="设备选择")]
    custom_output_dir: Annotated[bool, Field(False, title="自定义输出目录")]
    cache_dir: Annotated[str, Field("./cache", title="缓存路径")]
    output_dir: Annotated[str, Field("./output", title="输出路径")]
    asr_model_provider: Annotated[ASRModelProvider, Field("funasr", title="ASR 模型提供商")]
    funasr: Annotated[FunASRSettings, Field(FunASRSettings())]  # pyright: ignore[reportCallIssue]
    whisper: Annotated[WhisperSettings, Field(WhisperSettings())]  # pyright: ignore[reportCallIssue]
    _FIELD_TO_LITERAL = {
        "device": Device,
        "asr_model_provider": ASRModelProvider,
    }


# def main():
#     # 恢复默认配置
#     from lab.config_manager.config import (
#         XnneHangLabSettings,
#         load_settings_file,
#         search_for_settings_file,
#         write_settings_file,
#     )

#     funasr_path = search_for_settings_file("funasr.toml")
#     if funasr_path is not None and funasr_path.exists():
#         funasr_path.unlink()  # ensure load default
#     funasr_settings = load_settings_file("funasr.toml", FunASRSettings)
#     lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
#     lab_settings.funasr = funasr_settings
#     write_settings_file("lab.toml", lab_settings)
#     funasr_path = search_for_settings_file("funasr.toml")
#     if funasr_path is not None and funasr_path.exists():
#         funasr_path.unlink()

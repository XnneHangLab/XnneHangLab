from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from lab.config_manager.sherpa_asr import SherpaASRSettings
from lab.config_manager.webui_i18n_model import WebUIi18nSettings
from lab.streamlit.i18n import ASRModelProvider, Device, WhisperModelSize

WhisperSettingsTitle = Literal["whisper_models_base_dir", "whisper_model_size"]


class WhisperSettings(WebUIi18nSettings):
    whisper_models_base_dir: Annotated[str, Field("./models/whisper/", title="Whisper 模型存放目录")]
    whisper_model_size: Annotated[str, Field("turbo", title="Whisper 模型规格")]

    _I18N_FIELDS = {
        "whisper_model_size": WhisperModelSize,
    }


ASRSettingsTitle = Literal[
    "device",
    "custom_output_dir",
    "cache_dir",
    "output_dir",
    "asr_model_provider",
    "FFMPEG_PATH",
    "combine_line",
    "cut_line",
    "max_sentence_length",
]


class ASRSettings(WebUIi18nSettings):
    FFMPEG_PATH: Annotated[str, Field("ffmpeg", title="FFMPEG 路径")]
    device: Annotated[Literal["cpu", "cuda"], Field("cpu", title="设备选择")]
    custom_output_dir: Annotated[bool, Field(False, title="自定义输出目录")]
    cache_dir: Annotated[str, Field("./cache", title="缓存路径")]
    output_dir: Annotated[str, Field("./output", title="输出路径")]
    asr_model_provider: Annotated[str, Field("sherpa", title="ASR 模型提供商")]
    punctuation_list: Annotated[str, Field("，。；、？！,.;?!")]
    sherpa: Annotated[
        SherpaASRSettings,
        Field(default_factory=lambda: SherpaASRSettings()),  # pyright: ignore[reportCallIssue]
    ]
    whisper: Annotated[
        WhisperSettings,
        Field(default_factory=lambda: WhisperSettings()),  # pyright: ignore[reportCallIssue]
    ]
    cut: Annotated[bool, Field(False)]
    cut_line: Annotated[int, Field(400, title="切分间隔(毫秒)")]
    combine: Annotated[bool, Field(False)]
    combine_line: Annotated[int, Field(400, title="合并间隔(毫秒)")]
    max_sentence_length: Annotated[int, Field(20, title="最大单句长度")]

    _I18N_FIELDS = {
        "device": Device,
        "asr_model_provider": ASRModelProvider,
    }

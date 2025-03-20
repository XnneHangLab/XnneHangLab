from pydantic import BaseModel, Field
from typing import Annotated
from uiya._typing import Device


class RunnerBasicSettings(BaseModel):
    batch_size_s: Annotated[int, Field(300)]
    device: Annotated[Device, Field("cpu")]
    punctuation_list: Annotated[str, Field("，。；、？！,.;?!")]


class RunnerExtraSettings(BaseModel):
    cut: Annotated[bool, Field(False)]
    cut_line: Annotated[int, Field(500)]
    combine: Annotated[bool, Field(False)]
    combine_line: Annotated[int, Field(500)]
    max_sentence_length: Annotated[int, Field(20)]
    need_punc: Annotated[bool, Field(False)]


class RunnerPathSettings(BaseModel):
    hot_words_path: Annotated[str, Field("./hot_words.txt")]
    FFMPEG_PATH: Annotated[str, Field("ffmpeg")]
    base_model: Annotated[
        str,
        Field(
            "./models/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
        ),
    ]
    vad_model: Annotated[
        str, Field("./models/speech_fsmn_vad_zh-cn-16k-common-pytorch")
    ]
    punc_model: Annotated[
        str, Field("./models/punc_ct-transformer_zh-cn-common-vocab272727-pytorch")
    ]


class RunnerSettings(BaseModel):
    basic: Annotated[RunnerBasicSettings, Field(RunnerBasicSettings())]  # type: ignore
    paths: Annotated[RunnerPathSettings, Field(RunnerPathSettings())]  # type: ignore
    extra: Annotated[RunnerExtraSettings, Field(RunnerExtraSettings())]  # type: ignore

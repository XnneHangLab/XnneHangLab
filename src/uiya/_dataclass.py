from pydantic import BaseModel, Field
from typing import Annotated


class RunnerBasicSettings(BaseModel):
    batch_size_s: Annotated[int, Field(300)]
    device: Annotated[str, Field("cpu")]
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


# @dataclass
# class ConfigParser:
#     config = load_config()

#     batch_size_s: int = int(config["batch_size_s"])
#     max_workers: int = int(config["max_workers"])
#     device: str = str(config["device"])

#     need_punc: bool = bool(config["need_punc"])

#     cut_line: int = int(config["cut_line"])
#     cut: bool = bool(config["cut"])

#     max_sentence_length: int = int(config["max_sentence_length"])
#     combine_line: int = int(config["combine_line"])
#     combine: bool = bool(config["combine"])

#     punctuation_list: str = str(config["punctuation_list"])

#     base_model: Path = Path(str(config["base_model"]))
#     vad_model: Path = Path(str(config["vad_model"]))
#     punc_model: Path = Path(str(config["punc_model"]))
#     hot_words_path: Path = Path(str(config["hot_words_path"]))
#     FFMPEG_PATH: Path = Path(str(config["FFMPEG_PATH"]))

#     def __post_init__(self):
#         if not self.base_model.exists():
#             raise FileNotFoundError(f"{self.base_model} not found")
#         if not self.vad_model.exists():
#             raise FileNotFoundError(f"{self.vad_model} not found")
#         if not self.punc_model.exists():
#             raise FileNotFoundError(f"{self.punc_model} not found")
#         if not self.hot_words_path.exists():
#             # 创建空文件
#             self.hot_words_path.touch()
#             # TODO, 加上 Logger 告知用户没有检测到热词文件
#         # 运行 `ffmpeg -version` 检查是否安装了 ffmpeg,不需要打印输出
#         # 如果没有安装，抛出异常
#         if (
#             subprocess.run(
#                 [str(self.FFMPEG_PATH), "-version"],
#                 stdout=subprocess.PIPE,
#                 stderr=subprocess.PIPE,
#             ).returncode
#             != 0
#         ):
#             raise FileNotFoundError("FFMPEG not found")

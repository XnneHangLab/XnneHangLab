# (全局的)对外部开放的 api logic 都会在这里, 而不对外开放的比如 database logic 在对应的模块里

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict  # 添加 TypedDict 用于类型提示

# 将 funasr 和 whisper 导入移入 TYPE_CHECKING 或类中。
if TYPE_CHECKING:
    # 延迟导入的类型提示 (对于 MyPy/IDE)
    from funasr import AutoModel
    from whisper.model import Whisper


# 定义 FunASRModels 和 GlobalModelContainer
# ASRBaseModel.init_model() 的统一返回类型
class FunASRModels(TypedDict):
    asr: AutoModel | None
    vad: AutoModel | None
    asr_no_punc: AutoModel | None


# 全局模型容器的类型
class GlobalModelContainer(TypedDict):
    funasr: FunASRModels | None
    whisper: Whisper | None

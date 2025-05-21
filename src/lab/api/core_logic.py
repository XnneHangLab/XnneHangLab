from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from funasr import AutoModel  # 导入仍然在代码顶部，但只执行一次

from lab._dataclass import RunnerSettings
from lab.utils.config import load_settings_file
from lab.utils.console.logger import Logger
from lab.utils.model import generate_asr_results

if TYPE_CHECKING:
    from pathlib import Path

    from lab._typing import ASRResponse


class FunASRModel:  # 对于 api 需要快速响应, 不能 lazy-import ,所以独立出来一个版本.
    def __init__(self):
        self.settings = load_settings_file("global.toml", RunnerSettings)
        self.base_model: str = str(self.settings.base_model)
        self.vad_model: str = str(self.settings.vad_model)
        self.punc_model: str = str(self.settings.punc_model)
        self.sense_voice_model: str = str(self.settings.sense_voice_model)
        self.device: str = self.settings.device
        self._model = None  # 存储模型实例

    def asr_full_version(self):
        if self._model is None:  # 第一次加载时初始化模型
            Logger.info("Loading FunASR model...")
            self._model = AutoModel(
                model=self.base_model,
                vad_model=self.vad_model,
                punc_model=self.punc_model,
                device=self.device,
                disable_update=True,
            )
            Logger.info("FunASR model loaded successfully.")
        return self._model


# 全局模型实例（单例模式）
_model_instance = None


def load_model(only_text: bool = False) -> Any:
    """加载或获取 FunASR 模型（单例模式）"""
    global _model_instance
    if _model_instance is None:
        _model_instance = FunASRModel()
    return _model_instance.asr_full_version()


def rec_audio(
    input_path: Path,
    only_text: bool = False,
) -> dict[str, Any]:
    """处理音频文件并生成 SRT,返回结果信息"""
    model = load_model(only_text)
    start = time.time()
    # 生成 ASR 结果
    response: ASRResponse = generate_asr_results(model=model, input_path=input_path)
    end = time.time()
    processing_time = end - start
    result = {"processing_time": processing_time, "text": response["text"]}
    return result

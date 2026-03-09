from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from funasr import AutoModel
from loguru import logger

from lab.asr.asr_base_model import ASRBaseModel
from lab.asr.funasr.method import generate_asr_results, generate_vad_results
from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    from pathlib import Path

    from lab.api.types import FunASRModels
    from lab.asr.types import ASRResponse, VadResponse


class FunASRModel(ASRBaseModel):  # 对于 api 需要快速响应, 不能 lazy-import，所以独立出来一个版本.
    def __init__(self):
        self.settings = load_settings_file("lab.toml", XnneHangLabSettings)
        self.base_model: str = str(self.settings.asr.funasr.base_model)
        self.vad_model: str = str(self.settings.asr.funasr.vad_model)
        self.punc_model: str = str(self.settings.asr.funasr.punc_model)
        self.sense_voice_model: str = str(self.settings.asr.funasr.sense_voice_model)
        self.device: str = self.settings.asr.device
        self.model: FunASRModels = {"asr": None, "vad": None, "asr_no_punc": None}  # 存储模型实例

    def init_model(self):
        """初始化模型"""
        if self.model["asr"] is None:
            self.model["asr"] = self.asr_full_version()
        if self.model["vad"] is None:
            self.model["vad"] = self.only_vad_version()
        if self.model["asr_no_punc"] is None:
            self.model["asr_no_punc"] = self.asr_no_punc_version()
        return self.model

    def reload_model(self):
        self.model = {"asr": None, "vad": None, "asr_no_punc": None}  # 重置模型实例
        self.init_model()

    def forward(self, input_path: Path, use_punc: bool = True) -> dict[str, Any]:
        if self.model["asr"] is None or self.model["asr_no_punc"] is None:
            logger.error("punc 模型与 base 模型未初始化，请考虑模型文件路径配置是否正确。")
            raise ValueError("模型未初始化，请考虑模型文件路径配置是否正确。")

        start = time.time()
        response: ASRResponse = generate_asr_results(
            input_path=input_path,
            model=self.model["asr"] if use_punc else self.model["asr_no_punc"],
        )
        process_time = time.time() - start

        return {
            "key": response["key"],
            "text": response["text"],
            "timestamp": response["timestamp"],
            "process_time": process_time,
        }

    def vad_audio(self, input_path: Path) -> dict[str, Any]:
        if self.model["vad"] is None:
            logger.error("VAD 模型未初始化，请考虑模型文件路径配置是否正确。")
            raise ValueError("VAD 模型未初始化，请考虑模型文件路径配置是否正确。")
        start = time.time()
        response: VadResponse = generate_vad_results(
            input_path=input_path,
            model=self.model["vad"],
        )
        process_time = time.time() - start
        return {
            "key": response["key"],
            "process_time": process_time,
            "timestamp": response["timestamp"],
            "audio_length": response["audio_length"],
        }

    def asr_full_version(self):
        if self.model["asr"] is None:
            logger.info("Loading FunASR model...")
            self.model["asr"] = AutoModel(
                model=self.base_model,
                vad_model=self.vad_model,
                punc_model=self.punc_model,
                device=self.device,
                disable_update=True,
            )
            logger.info("ASR 模型加载成功!")
        return self.model["asr"]

    def asr_no_punc_version(self):
        if self.model["asr_no_punc"] is None:
            logger.info("Loading ASR no punc model...")
            self.model["asr_no_punc"] = AutoModel(
                model=self.base_model,
                device=self.device,
                disable_update=True,
            )
            logger.info("ASR no punc 模型加载成功!")
        return self.model["asr_no_punc"]

    def only_vad_version(self):
        """仅加载 VAD 模型"""
        if self.model["vad"] is None:
            logger.info("Loading VAD model...")
            self.model["vad"] = AutoModel(
                model=self.vad_model,
                device=self.device,
                disable_update=True,
            )
            logger.info("VAD 模型加载成功!")
            return self.model["vad"]


# ── 单例管理 ────────────────────────────────────────────────────────────────

_funasr_instance: FunASRModels | None = None


def load_funasr() -> FunASRModels | None:
    """加载或获取 FunASR 模型（单例）"""
    global _funasr_instance
    if _funasr_instance is None:
        lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
        if lab_settings.package.funasr:
            _funasr_instance = FunASRModel().init_model()
    return _funasr_instance


def reload_funasr() -> None:
    """重新加载 FunASR 模型"""
    global _funasr_instance
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    if lab_settings.package.funasr:
        m = FunASRModel()
        m.reload_model()
        _funasr_instance = m.model


def funasr_asr_audio(input_path: Path, need_punc: bool = True) -> dict[str, Any]:
    """对音频执行 ASR（FunASR）"""
    funasr_model = load_funasr()
    if funasr_model is None:
        raise ValueError("FunASR model instance is None. Please load the model first.")
    m = FunASRModel()
    m.model = funasr_model
    return m.forward(input_path, use_punc=need_punc)


def funasr_vad_audio(input_path: Path) -> dict[str, Any]:
    """对音频执行 VAD（FunASR）"""
    funasr_model = load_funasr()
    if funasr_model is None:
        raise ValueError("FunASR model instance is None. Please load the model first.")
    m = FunASRModel()
    m.model = funasr_model
    return m.vad_audio(input_path)

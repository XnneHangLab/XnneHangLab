# (全局的)对外部开放的 api logic 都会在这里, 而不对外开放的比如 database logic 在对应的模块里

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import whisper
from funasr import AutoModel
from loguru import logger  # 保持 loguru 在代码顶部导入

from lab.asr.asr_base_model import ASRBaseModel
from lab.asr.funasr.method import generate_asr_results, generate_vad_results
from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    from pathlib import Path

    from whisper.model import Whisper

    from lab._typing import ASRResponse, VadResponse
    from lab.api._typing import FunASRModels


class FunASRModel(ASRBaseModel):  # 对于 api 需要快速响应, 不能 lazy-import ,所以独立出来一个版本.
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
        if self.model["vad"] is None:  # 第一次加载时初始化模型
            logger.error("VAD 模型未初始化，请考虑模型文件路径配置是否正确。")
            raise ValueError("VAD 模型未初始化，请考虑模型文件路径配置是否正确。")
        start = time.time()
        response: VadResponse = generate_vad_results(
            input_path=input_path,
            model=self.model["vad"],
        )
        process_time = time.time() - start
        result = {
            "key": response["key"],
            "process_time": process_time,
            "timestamp": response["timestamp"],
            "audio_length": response["audio_length"],
        }
        return result

    def asr_full_version(self):
        if self.model["asr"] is None:  # 第一次加载时初始化模型
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
        if self.model["asr_no_punc"] is None:  # 第一次加载时初始化模型
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
        if self.model["vad"] is None:  # 第一次加载时初始化模型
            logger.info("Loading VAD model...")
            self.model["vad"] = AutoModel(
                model=self.vad_model,
                device=self.device,
                disable_update=True,
            )
            logger.info("VAD 模型加载成功!")
            return self.model["vad"]


class WhisperModel(ASRBaseModel):
    def __init__(self):
        # 假设配置管理器和配置路径正确
        self.settings = load_settings_file("lab.toml", XnneHangLabSettings)
        self.model_name: str = self.settings.asr.whisper.whisper_model_size
        self.device: str = self.settings.asr.device
        # Whisper 只需要一个 ASR 模型实例
        self.model: Whisper | None = None

    def init_model(self) -> Any:
        """初始化模型：如果模型未加载，则调用加载函数。"""
        if self.model is None:
            self.model = self._load_whisper_model()
        # 注意：这里我们返回模型实例字典以匹配 FunASR 的 init_model 签名，但主要目的是加载模型。
        return self.model

    def reload_model(self):
        """重新加载模型实例。"""
        self.model = None  # 重置模型实例
        self.init_model()

    def _load_whisper_model(self):
        """模型加载的具体实现"""
        logger.info(f"Loading Whisper model: {self.model_name} on device: {self.device}...")
        # 加载模型，可以根据配置调整精度
        model = whisper.load_model(
            self.model_name, device=self.device, download_root=self.settings.asr.whisper.whisper_models_base_dir
        )
        logger.info("Whisper 模型加载成功!")
        return model

    # ---------------------- 核心推理方法 ----------------------
    def forward(
        self,
        input_path: Path,
    ) -> dict[str, Any]:
        """
        执行 ASR 推理 (使用 Whisper)。
        """
        # 1. 确保模型已加载 (如果 init_model 尚未被调用)
        if self.model is None:
            logger.error("Whisper ASR 模型未加载或初始化失败。")
            raise ValueError("Whisper ASR 模型未加载或初始化失败。")

        model = self.model
        response = model.transcribe(str(input_path), word_timestamps=True)  # type: ignore
        return response  # type: ignore

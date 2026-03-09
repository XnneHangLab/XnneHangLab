from __future__ import annotations

from typing import TYPE_CHECKING, Any

import whisper
from loguru import logger

from lab.asr.asr_base_model import ASRBaseModel
from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    from pathlib import Path

    from whisper.model import Whisper


class WhisperModel(ASRBaseModel):
    def __init__(self):
        self.settings = load_settings_file("lab.toml", XnneHangLabSettings)
        self.model_name: str = self.settings.asr.whisper.whisper_model_size
        if self.model_name == "turbo":
            self.model_name = "large-v3-turbo"
        self.device: str = self.settings.asr.device
        self.model: Whisper | None = None

    def init_model(self) -> Any:
        """初始化模型"""
        if self.model is None:
            self.model = self._load_whisper_model()
        return self.model

    def reload_model(self):
        """重新加载模型实例"""
        self.model = None
        self.init_model()

    def _load_whisper_model(self):
        logger.info(f"Loading Whisper model: {self.model_name} on device: {self.device}...")
        model = whisper.load_model(
            self.model_name,
            device=self.device,
            download_root=self.settings.asr.whisper.whisper_models_base_dir,
        )
        logger.info("Whisper 模型加载成功!")
        return model

    def forward(self, input_path: Path) -> dict[str, Any]:
        if self.model is None:
            logger.error("Whisper ASR 模型未加载或初始化失败。")
            raise ValueError("Whisper ASR 模型未加载或初始化失败。")
        response = self.model.transcribe(str(input_path), word_timestamps=True)  # type: ignore
        return response  # type: ignore


# ── 单例管理 ────────────────────────────────────────────────────────────────

_whisper_instance: Whisper | None = None


def load_whisper() -> Whisper | None:
    """加载或获取 Whisper 模型（单例）"""
    global _whisper_instance
    if _whisper_instance is None:
        lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
        if lab_settings.package.whisper:
            _whisper_instance = WhisperModel().init_model()
    return _whisper_instance


def reload_whisper() -> None:
    """重新加载 Whisper 模型"""
    global _whisper_instance
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    if lab_settings.package.whisper:
        m = WhisperModel()
        m.reload_model()
        _whisper_instance = m.model


def whisper_asr_audio(input_path: Path) -> dict[str, Any]:
    """对音频执行 ASR（Whisper）"""
    whisper_model = load_whisper()
    if whisper_model is None:
        raise ValueError("Whisper model instance is None. Please load the model first.")
    m = WhisperModel()
    m.model = whisper_model
    return m.forward(input_path)

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lab.api.logic.faster_qwen_tts import init_qwen_tts_model
    from lab.api.logic.qwen_asr import load_qwen_asr_engine, qwen_asr_transcribe, reload_qwen_asr_engine
    from lab.api.logic.sherpa_asr import load_sherpa_asr, reload_sherpa_asr, sherpa_asr_audio, sherpa_vad_audio
    from lab.api.logic.translate import TranslateEngineRouter

_EXPORT_MAP: dict[str, tuple[str, str]] = {
    "init_qwen_tts_model": ("lab.api.logic.faster_qwen_tts", "init_qwen_tts_model"),
    "sherpa_asr_audio": ("lab.api.logic.sherpa_asr", "sherpa_asr_audio"),
    "sherpa_vad_audio": ("lab.api.logic.sherpa_asr", "sherpa_vad_audio"),
    "load_sherpa_asr": ("lab.api.logic.sherpa_asr", "load_sherpa_asr"),
    "reload_sherpa_asr": ("lab.api.logic.sherpa_asr", "reload_sherpa_asr"),
    "load_qwen_asr_engine": ("lab.api.logic.qwen_asr", "load_qwen_asr_engine"),
    "reload_qwen_asr_engine": ("lab.api.logic.qwen_asr", "reload_qwen_asr_engine"),
    "qwen_asr_transcribe": ("lab.api.logic.qwen_asr", "qwen_asr_transcribe"),
    "TranslateEngineRouter": ("lab.api.logic.translate", "TranslateEngineRouter"),
}

__all__ = [
    "init_qwen_tts_model",
    "sherpa_asr_audio",
    "sherpa_vad_audio",
    "qwen_asr_transcribe",
    "load_sherpa_asr",
    "load_qwen_asr_engine",
    "reload_sherpa_asr",
    "reload_qwen_asr_engine",
    "TranslateEngineRouter",
]


def __getattr__(name: str) -> Any:
    """按需导入 `lab.api.logic` 对外暴露的符号。

    Args:
        name: 待访问的导出名。

    Returns:
        Any: 实际导出的函数或对象。

    Raises:
        AttributeError: 访问未知导出名时抛出。
    """
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value

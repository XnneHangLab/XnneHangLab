from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lab.api.logic.faster_qwen_tts import init_qwen_tts_model
    from lab.api.logic.funasr import funasr_asr_audio, funasr_vad_audio, load_funasr, reload_funasr
    from lab.api.logic.whisper import load_whisper, reload_whisper, whisper_asr_audio

_EXPORT_MAP: dict[str, tuple[str, str]] = {
    "init_qwen_tts_model": ("lab.api.logic.faster_qwen_tts", "init_qwen_tts_model"),
    "funasr_asr_audio": ("lab.api.logic.funasr", "funasr_asr_audio"),
    "funasr_vad_audio": ("lab.api.logic.funasr", "funasr_vad_audio"),
    "load_funasr": ("lab.api.logic.funasr", "load_funasr"),
    "reload_funasr": ("lab.api.logic.funasr", "reload_funasr"),
    "load_whisper": ("lab.api.logic.whisper", "load_whisper"),
    "reload_whisper": ("lab.api.logic.whisper", "reload_whisper"),
    "whisper_asr_audio": ("lab.api.logic.whisper", "whisper_asr_audio"),
}

__all__ = [
    "init_qwen_tts_model",
    "funasr_asr_audio",
    "funasr_vad_audio",
    "whisper_asr_audio",
    "load_funasr",
    "load_whisper",
    "reload_funasr",
    "reload_whisper",
]


def __getattr__(name: str) -> Any:
    """按需导入 `lab.api.logic` 对外暴露的符号。

    这样可以保留原有 `from lab.api.logic import ...` 的使用方式，同时避免
    仅为访问单个逻辑模块就把其他重量级依赖一并加载进来。

    Args:
        name: 被访问的导出符号名称。

    Returns:
        Any: 目标模块中的实际对象。

    Raises:
        AttributeError: 访问的符号不在导出映射中时抛出。
    """
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value

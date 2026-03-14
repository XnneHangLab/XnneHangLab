from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from lab.asr.qwen_asr.engine import get_qwen_asr, load_qwen_asr, reset_qwen_asr_engine
from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    from pathlib import Path


def load_qwen_asr_engine() -> None:
    """预加载 Qwen3-ASR 引擎。

    Args:
        None.

    Returns:
        None.

    Raises:
        RuntimeError: 模型加载失败时抛出。
    """
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    qwen_settings = lab_settings.asr.qwen_asr
    load_qwen_asr(model_id=qwen_settings.model_id, device=qwen_settings.device)


def qwen_asr_transcribe(input_path: Path) -> dict[str, Any]:
    """执行 Qwen3-ASR 推理。

    Args:
        input_path: 输入音频路径。

    Returns:
        dict[str, Any]: 包含 key、text、timestamp、process_time 的结果字典。

    Raises:
        FileNotFoundError: 音频文件不存在时抛出。
        RuntimeError: 推理失败时抛出。
    """
    start = time.perf_counter()
    try:
        engine = get_qwen_asr()
    except RuntimeError:
        load_qwen_asr_engine()
        engine = get_qwen_asr()

    response = engine.transcribe(input_path)
    process_time = time.perf_counter() - start

    return {
        "key": response["key"],
        "text": response["text"],
        "timestamp": response["timestamp"],
        "process_time": process_time,
    }


def reload_qwen_asr_engine() -> None:
    """重新加载 Qwen3-ASR 引擎。

    Args:
        None.

    Returns:
        None.

    Raises:
        RuntimeError: 模型重新加载失败时抛出。
    """
    reset_qwen_asr_engine()
    load_qwen_asr_engine()

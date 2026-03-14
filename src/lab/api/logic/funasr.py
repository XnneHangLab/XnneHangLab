from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from lab.asr.sherpa.engine import (
    get_sherpa_asr,
    get_sherpa_vad,
    load_sherpa_asr,
    load_sherpa_vad,
    reset_sherpa_engines,
)
from lab.config_manager import XnneHangLabSettings, load_settings_file


def load_funasr() -> None:
    """预加载 ASR 和 VAD 引擎（在 server lifespan 调用）。

    读取 `lab_settings.asr.sherpa` 配置，初始化 `SherpaASREngine`
    和 `SherpaVADEngine` 单例。

    Args:
        None.

    Returns:
        None.

    Raises:
        FileNotFoundError: sherpa-onnx 模型路径不存在时抛出。
    """
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    sherpa_settings = lab_settings.asr.sherpa

    load_sherpa_asr(
        model_dir=Path(sherpa_settings.asr_model_dir),
        num_threads=sherpa_settings.num_threads,
    )
    load_sherpa_vad(vad_model_path=Path(sherpa_settings.vad_model_path))


def funasr_asr_audio(input_path: Path) -> dict[str, Any]:
    """执行 ASR 推理（sherpa-onnx）。

    Args:
        input_path: 输入音频文件路径。

    Returns:
        dict[str, Any]: 包含 key、text、timestamp、process_time 的结果字典。

    Raises:
        FileNotFoundError: 音频文件不存在时抛出。
        RuntimeError: sherpa-onnx 推理失败时抛出。
    """
    start = time.perf_counter()
    response = get_sherpa_asr().transcribe(input_path)
    process_time = time.perf_counter() - start

    return {
        "key": response["key"],
        "text": response["text"],
        "timestamp": response["timestamp"],
        "process_time": process_time,
    }


def funasr_vad_audio(input_path: Path) -> dict[str, Any]:
    """执行 VAD 检测（sherpa-onnx）。

    Args:
        input_path: 输入音频文件路径。

    Returns:
        dict[str, Any]: 包含 key、timestamp、audio_length、process_time 的结果字典。

    Raises:
        FileNotFoundError: 音频文件不存在时抛出。
        RuntimeError: sherpa-onnx VAD 推理失败时抛出。
    """
    start = time.perf_counter()
    response = get_sherpa_vad().detect(input_path)
    process_time = time.perf_counter() - start

    return {
        "key": response["key"],
        "timestamp": response["timestamp"],
        "audio_length": response["audio_length"],
        "process_time": process_time,
    }


def reload_funasr() -> None:
    """重新加载 ASR 和 VAD 引擎。

    Args:
        None.

    Returns:
        None.

    Raises:
        FileNotFoundError: sherpa-onnx 模型路径不存在时抛出。
    """
    reset_sherpa_engines()
    load_funasr()

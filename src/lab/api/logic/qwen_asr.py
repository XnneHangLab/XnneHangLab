from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from lab.asr.qwen_asr.engine import get_qwen_asr, load_qwen_asr, reset_qwen_asr_engine
from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    from pathlib import Path

    from lab.config_manager.qwen_asr import QwenASRModelName


def _get_qwen_settings() -> XnneHangLabSettings:
    """读取 lab.toml 中的当前配置。

    Args:
        None.

    Returns:
        XnneHangLabSettings: 当前实验室配置。

    Raises:
        None.
    """
    return load_settings_file("lab.toml", XnneHangLabSettings)


def _is_qwen_model_enabled(model_name: QwenASRModelName, settings: XnneHangLabSettings) -> bool:
    """判断指定 Qwen3-ASR 模型是否已启用。

    Args:
        model_name: 模型规格名称。
        settings: 当前配置。

    Returns:
        bool: 是否启用。

    Raises:
        None.
    """
    if model_name == "0.6b":
        return settings.package.qwen_asr_0_6b
    return settings.package.qwen_asr_1_7b


def _get_qwen_model_path(model_name: QwenASRModelName, settings: XnneHangLabSettings) -> str:
    """读取指定模型的本地路径。

    Args:
        model_name: 模型规格名称。
        settings: 当前配置。

    Returns:
        str: 本地模型路径。

    Raises:
        RuntimeError: 指定模型未启用时抛出。
    """
    if not _is_qwen_model_enabled(model_name, settings):
        raise RuntimeError(f"Qwen3-ASR {model_name} is disabled in lab.toml")

    if model_name == "0.6b":
        return settings.asr.qwen_asr.model_0_6b_path
    return settings.asr.qwen_asr.model_1_7b_path


def _get_active_qwen_model(settings: XnneHangLabSettings) -> QwenASRModelName:
    """读取当前激活的 Qwen3-ASR 模型。

    Args:
        settings: 当前配置。

    Returns:
        QwenASRModelName: 当前启用的模型规格。

    Raises:
        RuntimeError: 当前激活模型未启用时抛出。
    """
    active_model = settings.asr.qwen_asr.active_model
    if not _is_qwen_model_enabled(active_model, settings):
        raise RuntimeError(
            f"Qwen3-ASR active model `{active_model}` is disabled in lab.toml. Enable the matching package flag first."
        )
    return active_model


def load_qwen_asr_engine(model_name: QwenASRModelName | None = None) -> None:
    """预加载 Qwen3-ASR 引擎。

    Args:
        model_name: 可选的模型规格；为空时使用当前 active_model。

    Returns:
        None.

    Raises:
        RuntimeError: 模型加载失败时抛出。
    """
    settings = _get_qwen_settings()
    selected_model = model_name or _get_active_qwen_model(settings)
    qwen_settings = settings.asr.qwen_asr
    model_path = _get_qwen_model_path(selected_model, settings)
    load_qwen_asr(model_path=model_path, device=qwen_settings.device)


def preload_enabled_qwen_asr_engines() -> list[QwenASRModelName]:
    """预加载所有已启用的 Qwen3-ASR 模型。

    Args:
        None.

    Returns:
        list[QwenASRModelName]: 本次成功触发加载的模型列表。

    Raises:
        RuntimeError: 模型加载失败时抛出。
    """
    settings = _get_qwen_settings()
    loaded_models: list[QwenASRModelName] = []

    if settings.package.qwen_asr_0_6b:
        load_qwen_asr_engine("0.6b")
        loaded_models.append("0.6b")

    if settings.package.qwen_asr_1_7b:
        load_qwen_asr_engine("1.7b")
        loaded_models.append("1.7b")

    return loaded_models


def qwen_asr_transcribe(input_path: Path) -> dict[str, Any]:
    """执行 Qwen3-ASR 推理。

    Args:
        input_path: 输入音频路径。

    Returns:
        dict[str, Any]: 包含 key、text、timestamp、process_time 的结果。

    Raises:
        FileNotFoundError: 音频文件不存在时抛出。
        RuntimeError: 推理失败时抛出。
    """
    start = time.perf_counter()
    settings = _get_qwen_settings()
    qwen_settings = settings.asr.qwen_asr
    active_model = _get_active_qwen_model(settings)
    model_path = _get_qwen_model_path(active_model, settings)

    try:
        engine = get_qwen_asr(model_path=model_path, device=qwen_settings.device)
    except RuntimeError:
        load_qwen_asr(model_path=model_path, device=qwen_settings.device)
        engine = get_qwen_asr(model_path=model_path, device=qwen_settings.device)

    response = engine.transcribe(input_path)
    process_time = time.perf_counter() - start

    return {
        "key": response["key"],
        "text": response["text"],
        "timestamp": response["timestamp"],
        "process_time": process_time,
    }


def reload_qwen_asr_engine(model_name: QwenASRModelName | None = None) -> None:
    """重新加载指定或当前激活的 Qwen3-ASR 引擎。

    Args:
        model_name: 可选的模型规格；为空时使用当前 active_model。

    Returns:
        None.

    Raises:
        RuntimeError: 模型重新加载失败时抛出。
    """
    settings = _get_qwen_settings()
    selected_model = model_name or _get_active_qwen_model(settings)
    qwen_settings = settings.asr.qwen_asr
    model_path = _get_qwen_model_path(selected_model, settings)
    reset_qwen_asr_engine(model_path=model_path, device=qwen_settings.device)
    load_qwen_asr(model_path=model_path, device=qwen_settings.device)

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import HTTPException
from loguru import logger

MODEL_NAME = "Qwen/Qwen3-TTS-1.7B"

_tts_logger = logger.bind(group="tts")
_qwen_tts_engine: Any | None = None


def _init_engine() -> Any:
    """初始化 faster-qwen3-tts 引擎（全局单例）。"""
    global _qwen_tts_engine
    if _qwen_tts_engine is not None:
        return _qwen_tts_engine

    try:
        import faster_qwen3_tts as fq
    except Exception as exc:  # pragma: no cover - 依赖未安装时的保护
        raise RuntimeError("faster-qwen3-tts is not installed") from exc

    constructors: list[tuple[str, Any]] = [
        ("Qwen3TTS", getattr(fq, "Qwen3TTS", None)),
        ("FasterQwen3TTS", getattr(fq, "FasterQwen3TTS", None)),
    ]

    for ctor_name, ctor in constructors:
        if ctor is None:
            continue
        try:
            _qwen_tts_engine = ctor.from_pretrained(MODEL_NAME)
            _tts_logger.info(f"faster-qwen-tts model initialized via {ctor_name}.from_pretrained")
            return _qwen_tts_engine
        except Exception:
            try:
                _qwen_tts_engine = ctor(model_name=MODEL_NAME)
                _tts_logger.info(f"faster-qwen-tts model initialized via {ctor_name}(model_name=...)")
                return _qwen_tts_engine
            except Exception:
                continue

    raise RuntimeError("Unsupported faster-qwen3-tts API. Please update logic initializer.")


def init_qwen_tts_model() -> None:
    _init_engine()


def get_qwen_tts_model() -> Any:
    if _qwen_tts_engine is None:
        raise HTTPException(status_code=503, detail="Qwen-TTS model not initialized")
    return _qwen_tts_engine


def _as_wav_bytes(payload: Any, *, sample_rate: int = 24000) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)

    audio_data: Any = payload
    sr = sample_rate

    if isinstance(payload, dict):
        audio_data = payload.get("audio", payload.get("wav", payload.get("samples", payload)))
        sr_raw = payload.get("sample_rate", payload.get("sr", sample_rate))
        if isinstance(sr_raw, int):
            sr = sr_raw

    arr = np.asarray(audio_data, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)

    with BytesIO() as buffer:
        sf.write(buffer, arr, samplerate=sr, format="WAV")
        return buffer.getvalue()


def synthesize_once(*, text: str, ref_audio: Path | None, ref_text: str | None) -> bytes:
    """非流式一次性合成，返回 WAV bytes。"""
    engine = get_qwen_tts_model()

    kwargs: dict[str, Any] = {"text": text, "stream": False}
    if ref_audio is not None:
        kwargs["ref_audio"] = str(ref_audio)
    if ref_text:
        kwargs["ref_text"] = ref_text

    for method_name in ("tts", "synthesize", "generate"):
        method = getattr(engine, method_name, None)
        if method is None:
            continue
        try:
            result = method(**kwargs)
            return _as_wav_bytes(result)
        except TypeError:
            # 部分版本参数名不兼容，降级使用 prompt_audio / prompt_text
            fallback_kwargs = dict(kwargs)
            if "ref_audio" in fallback_kwargs:
                fallback_kwargs["prompt_audio"] = fallback_kwargs.pop("ref_audio")
            if "ref_text" in fallback_kwargs:
                fallback_kwargs["prompt_text"] = fallback_kwargs.pop("ref_text")
            result = method(**fallback_kwargs)
            return _as_wav_bytes(result)

    raise HTTPException(status_code=500, detail="No usable synth method found on qwen tts engine")


def synthesize_stream(*, text: str, ref_audio: Path | None, ref_text: str | None) -> Iterator[bytes]:
    """流式合成，逐段返回音频 bytes。"""
    engine = get_qwen_tts_model()

    kwargs: dict[str, Any] = {"text": text, "stream": True}
    if ref_audio is not None:
        kwargs["ref_audio"] = str(ref_audio)
    if ref_text:
        kwargs["ref_text"] = ref_text

    for method_name in ("tts", "synthesize", "generate"):
        method = getattr(engine, method_name, None)
        if method is None:
            continue
        try:
            stream_result = method(**kwargs)
        except TypeError:
            fallback_kwargs = dict(kwargs)
            if "ref_audio" in fallback_kwargs:
                fallback_kwargs["prompt_audio"] = fallback_kwargs.pop("ref_audio")
            if "ref_text" in fallback_kwargs:
                fallback_kwargs["prompt_text"] = fallback_kwargs.pop("ref_text")
            stream_result = method(**fallback_kwargs)

        if hasattr(stream_result, "__iter__"):
            for chunk in stream_result:
                if isinstance(chunk, bytes):
                    yield chunk
                else:
                    yield _as_wav_bytes(chunk)
            return

    raise HTTPException(status_code=500, detail="No usable stream synth method found on qwen tts engine")

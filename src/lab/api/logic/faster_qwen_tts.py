from __future__ import annotations

import os
import struct
import threading
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

import numpy as np
from fastapi import HTTPException
from loguru import logger

DEFAULT_MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
DEFAULT_SAMPLE_RATE = 24000

_tts_logger = logger.bind(group="tts")
_qwen_tts_engine: Any | None = None
_sample_rate: int = DEFAULT_SAMPLE_RATE
_model_lock = threading.Lock()


def resolve_model_name() -> str:
    """解析模型来源：环境变量 > 本地目录 > HuggingFace 模型 ID。"""
    if env_model := os.environ.get("XNNEHANG_QWEN_TTS_MODEL", "").strip():
        return env_model

    local_candidates = [
        Path("./models/Qwen3-TTS-12Hz-1.7B-Base"),
        Path("./models/Qwen3-TTS-1.7B-Base"),
        Path("./models/Qwen/Qwen3-TTS-12Hz-1.7B-Base"),
        Path("./models/Qwen/Qwen3-TTS-1.7B-Base"),
    ]
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate.resolve())

    return DEFAULT_MODEL_NAME


def _resolve_device() -> str:
    if device := os.environ.get("XNNEHANG_QWEN_TTS_DEVICE", "").strip():
        return device

    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _init_engine() -> Any:
    """初始化 faster-qwen3-tts 引擎（全局单例）。"""
    global _qwen_tts_engine, _sample_rate
    if _qwen_tts_engine is not None:
        return _qwen_tts_engine

    try:
        from faster_qwen3_tts import FasterQwen3TTS
    except Exception as exc:  # pragma: no cover - 依赖未安装时的保护
        raise RuntimeError("faster-qwen3-tts is not installed") from exc

    model_name = resolve_model_name()
    device = _resolve_device()
    _tts_logger.info(f"qwen-tts model source: {model_name}")
    _tts_logger.info(f"qwen-tts model device: {device}")

    kwargs: dict[str, Any] = {"device": device}
    if device == "cuda":
        try:
            import torch

            kwargs["dtype"] = torch.bfloat16
        except Exception:
            pass

    _qwen_tts_engine = FasterQwen3TTS.from_pretrained(model_name, **kwargs)

    warmup_fn = getattr(_qwen_tts_engine, "_warmup", None)
    if callable(warmup_fn):
        try:
            _tts_logger.info("warming up qwen-tts model (cuda graphs)...")
            warmup_fn(prefill_len=100)
            _tts_logger.info("qwen-tts warmup done")
        except Exception:
            _tts_logger.warning("qwen-tts warmup failed, continue without warmup")

    sample_rate_raw = getattr(_qwen_tts_engine, "sample_rate", DEFAULT_SAMPLE_RATE)
    _sample_rate = int(sample_rate_raw) if isinstance(sample_rate_raw, int | float) else DEFAULT_SAMPLE_RATE

    _tts_logger.info(f"faster-qwen-tts model initialized. sample_rate={_sample_rate}")
    return _qwen_tts_engine


def init_qwen_tts_model() -> None:
    _init_engine()


def get_qwen_tts_model() -> Any:
    if _qwen_tts_engine is None:
        raise HTTPException(status_code=503, detail="Qwen-TTS model not initialized")
    return _qwen_tts_engine


def get_sample_rate() -> int:
    return _sample_rate


def _to_pcm16(pcm: np.ndarray | Any) -> bytes:
    """把 chunk 转成 int16 PCM，避免重复缩放导致机械音。"""
    arr_any: Any = pcm
    if hasattr(arr_any, "detach"):
        arr_any = arr_any.detach()
    if hasattr(arr_any, "cpu"):
        arr_any = arr_any.cpu()
    if hasattr(arr_any, "numpy"):
        arr_any = arr_any.numpy()

    arr = np.asarray(arr_any)
    if arr.ndim > 1:
        arr = arr.reshape(-1)

    if np.issubdtype(arr.dtype, np.integer):
        return np.clip(arr, -32768, 32767).astype(np.int16).tobytes()

    arr_f = arr.astype(np.float32)
    peak = float(np.max(np.abs(arr_f))) if arr_f.size else 0.0

    if peak <= 1.5:
        pcm16 = np.clip(arr_f * 32768.0, -32768, 32767).astype(np.int16)
    else:
        # 某些实现可能已输出接近 PCM16 的数值范围
        pcm16 = np.clip(arr_f, -32768, 32767).astype(np.int16)
    return pcm16.tobytes()


def _concat_audio(audio_list: Any) -> np.ndarray:
    """对齐官方 demo：把多段音频拼接为一段 float32。"""
    if isinstance(audio_list, np.ndarray):
        return audio_list.astype(np.float32).squeeze()

    parts: list[np.ndarray] = []
    try:
        for chunk in audio_list:
            arr = np.asarray(chunk, dtype=np.float32).squeeze()
            if arr.size > 0:
                parts.append(arr)
    except TypeError:
        arr = np.asarray(audio_list, dtype=np.float32).squeeze()
        if arr.size > 0:
            parts.append(arr)

    if not parts:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(parts)


def _wav_header(sample_rate: int, data_len: int = 0xFFFFFFFF) -> bytes:
    n_channels = 1
    bits = 16
    byte_rate = sample_rate * n_channels * bits // 8
    block_align = n_channels * bits // 8
    riff_size = 0xFFFFFFFF if data_len == 0xFFFFFFFF else 36 + data_len
    buf = BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", riff_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, n_channels, sample_rate, byte_rate, block_align, bits))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_len))
    return buf.getvalue()


def _to_wav_bytes(pcm: np.ndarray, sample_rate: int) -> bytes:
    raw = _to_pcm16(pcm)
    return _wav_header(sample_rate, len(raw)) + raw


def _resolve_ref(ref_audio: Path | None, ref_text: str | None) -> tuple[str | None, str]:
    ref_audio_str = str(ref_audio) if ref_audio is not None else None
    return ref_audio_str, ref_text or ""


def synthesize_once(*, text: str, ref_audio: Path | None, ref_text: str | None) -> bytes:
    """非流式一次性合成，返回完整 WAV bytes。"""
    model = get_qwen_tts_model()
    ref_audio_str, ref_text_str = _resolve_ref(ref_audio, ref_text)

    with _model_lock:
        audio_arrays, sample_rate = model.generate_voice_clone(
            text=text,
            language="Auto",
            ref_audio=ref_audio_str,
            ref_text=ref_text_str,
        )

    audio = _concat_audio(audio_arrays)
    if audio.size == 0:
        audio = np.zeros(1, dtype=np.float32)
    sr = int(sample_rate) if isinstance(sample_rate, int | float) else get_sample_rate()
    return _to_wav_bytes(audio, sr)


def synthesize_stream(*, text: str, ref_audio: Path | None, ref_text: str | None) -> Iterator[bytes]:
    """流式合成，返回 `wav header + pcm chunks`。"""
    model = get_qwen_tts_model()
    ref_audio_str, ref_text_str = _resolve_ref(ref_audio, ref_text)

    yield _wav_header(get_sample_rate())

    with _model_lock:
        for chunk, _sr, _timing in model.generate_voice_clone_streaming(
            text=text,
            language="Auto",
            ref_audio=ref_audio_str,
            ref_text=ref_text_str,
            chunk_size=8,
            non_streaming_mode=False,
        ):
            yield _to_pcm16(_concat_audio(chunk))

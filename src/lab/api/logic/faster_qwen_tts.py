from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import numpy as np
import soundfile as sf
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
    except Exception as exc:  # pragma: no cover
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
    _sample_rate = int(sample_rate_raw) if isinstance(sample_rate_raw, (int, float)) else DEFAULT_SAMPLE_RATE

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


def _to_wav_chunk(pcm: np.ndarray, sample_rate: int) -> bytes:
    """把 float32 音频写成完整独立 WAV bytes。"""
    buf = io.BytesIO()
    sf.write(buf, pcm, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _to_wav_b64(pcm: np.ndarray, sample_rate: int) -> str:
    wav_bytes = _to_wav_chunk(pcm, sample_rate)
    return base64.b64encode(wav_bytes).decode("utf-8")


def _concat_audio(audio_list: Any) -> np.ndarray:
    """把多段音频拼接为一段 float32。"""
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


def _to_wav_bytes(pcm: np.ndarray, sample_rate: int) -> bytes:
    """非流式：生成完整 WAV。"""
    return _to_wav_chunk(pcm, sample_rate)


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
    sr = int(sample_rate) if isinstance(sample_rate, (int, float)) else get_sample_rate()
    return _to_wav_bytes(audio, sr)


async def synthesize_stream(*, text: str, ref_audio: Path | None, ref_text: str | None) -> AsyncIterator[str]:
    """
    流式合成：返回 SSE 文本事件。
    每个 chunk 都是一个 JSON payload，audio_b64 是完整独立 WAV。
    完全对齐官方 demo 的传输思路，而不是直接输出 raw wav byte stream。
    """
    model = get_qwen_tts_model()
    ref_audio_str, ref_text_str = _resolve_ref(ref_audio, ref_text)

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _run_inference() -> None:
        try:
            t0 = time.perf_counter()
            total_audio_s = 0.0
            total_gen_ms = 0.0
            ttfa_ms: float | None = None
            voice_clone_ms = 0.0

            with _model_lock:
                gen = model.generate_voice_clone_streaming(
                    text=text,
                    language="Auto",
                    ref_audio=ref_audio_str,
                    ref_text=ref_text_str,
                    chunk_size=8,
                    non_streaming_mode=False,
                )

                first_audio = next(gen, None)
                if first_audio is not None:
                    audio_chunk, sr, timing = first_audio
                    sr = int(sr) if isinstance(sr, (int, float)) else get_sample_rate()

                    wall_first_ms = (time.perf_counter() - t0) * 1000.0
                    model_ms = float(timing.get("prefill_ms", 0.0)) + float(timing.get("decode_ms", 0.0))
                    voice_clone_ms = max(0.0, wall_first_ms - model_ms)

                    total_gen_ms += model_ms
                    if ttfa_ms is None:
                        ttfa_ms = total_gen_ms

                    audio_chunk = _concat_audio(audio_chunk)
                    if audio_chunk.size > 0:
                        dur = len(audio_chunk) / sr
                        total_audio_s += dur
                        rtf = total_audio_s / (total_gen_ms / 1000.0) if total_gen_ms > 0 else 0.0

                        payload = {
                            "type": "chunk",
                            "audio_b64": _to_wav_b64(audio_chunk, sr),
                            "sample_rate": sr,
                            "ttfa_ms": round(ttfa_ms),
                            "voice_clone_ms": round(voice_clone_ms),
                            "rtf": round(rtf, 3),
                            "total_audio_s": round(total_audio_s, 3),
                            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0),
                        }
                        loop.call_soon_threadsafe(queue.put_nowait, json.dumps(payload))

                for audio_chunk, sr, timing in gen:
                    sr = int(sr) if isinstance(sr, (int, float)) else get_sample_rate()

                    total_gen_ms += float(timing.get("prefill_ms", 0.0)) + float(timing.get("decode_ms", 0.0))
                    if ttfa_ms is None:
                        ttfa_ms = total_gen_ms

                    audio_chunk = _concat_audio(audio_chunk)
                    if audio_chunk.size == 0:
                        continue

                    dur = len(audio_chunk) / sr
                    total_audio_s += dur
                    rtf = total_audio_s / (total_gen_ms / 1000.0) if total_gen_ms > 0 else 0.0

                    payload = {
                        "type": "chunk",
                        "audio_b64": _to_wav_b64(audio_chunk, sr),
                        "sample_rate": sr,
                        "ttfa_ms": round(ttfa_ms),
                        "voice_clone_ms": round(voice_clone_ms),
                        "rtf": round(rtf, 3),
                        "total_audio_s": round(total_audio_s, 3),
                        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0),
                    }
                    loop.call_soon_threadsafe(queue.put_nowait, json.dumps(payload))

            final_rtf = total_audio_s / (total_gen_ms / 1000.0) if total_gen_ms > 0 else 0.0
            done_payload = {
                "type": "done",
                "ttfa_ms": round(ttfa_ms) if ttfa_ms is not None else 0,
                "voice_clone_ms": round(voice_clone_ms),
                "rtf": round(final_rtf, 3),
                "total_audio_s": round(total_audio_s, 3),
                "total_ms": round((time.perf_counter() - t0) * 1000.0),
            }
            loop.call_soon_threadsafe(queue.put_nowait, json.dumps(done_payload))

        except Exception as exc:
            _tts_logger.exception("streaming inference failed")
            err_payload = {
                "type": "error",
                "message": str(exc),
            }
            loop.call_soon_threadsafe(queue.put_nowait, json.dumps(err_payload))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_run_inference, daemon=True).start()

    while True:
        msg = await queue.get()
        if msg is None:
            break
        yield f"data: {msg}\n\n"

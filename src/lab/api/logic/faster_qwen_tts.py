from __future__ import annotations

import asyncio
import base64
import gc
import hashlib
import io
import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import soundfile as sf
from fastapi import HTTPException
from loguru import logger
from numpy.typing import NDArray

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.conversations.tts_manager import resolve_all_voice_assets, resolve_voice_assets
from lab.profile.schema import Profile

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from lab.config_manager.qwen_tts import QwenTTSModelName

DEFAULT_SAMPLE_RATE = 24000  # https://github.com/andimarafioti/faster-qwen3-tts/issues/50
DEFAULT_MODEL_SOURCES = {
    "0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
}

Float32Array = NDArray[np.float32]

_tts_logger = logger.bind(group="tts")
_qwen_tts_engine: Any | None = None
_loaded_model_name: QwenTTSModelName | None = None
_loaded_model_source: str | None = None
_sample_rate: int = DEFAULT_SAMPLE_RATE
_model_lock = threading.Lock()
_MAX_CACHED_VOICE_PROMPTS = 10
_voice_prompt_cache: OrderedDict[tuple[bytes, str], Any] = OrderedDict()


def _get_qwen_tts_settings() -> XnneHangLabSettings:
    return load_settings_file("lab.toml", XnneHangLabSettings)


def normalize_qwen_tts_model_name(model_name: str) -> QwenTTSModelName:
    normalized = model_name.strip().lower()
    aliases = {
        "0.6b": "0.6b",
        "0.6": "0.6b",
        "qwen3-tts-12hz-0.6b-base": "0.6b",
        "qwen/qwen3-tts-12hz-0.6b-base": "0.6b",
        "1.7b": "1.7b",
        "1.7": "1.7b",
        "qwen3-tts-12hz-1.7b-base": "1.7b",
        "qwen/qwen3-tts-12hz-1.7b-base": "1.7b",
    }
    resolved = aliases.get(normalized)
    if resolved is None:
        raise RuntimeError(f"Unsupported Qwen-TTS model: {model_name}")
    return cast("QwenTTSModelName", resolved)


def get_configured_qwen_tts_model_name(settings: XnneHangLabSettings | None = None) -> QwenTTSModelName:
    return (settings or _get_qwen_tts_settings()).agent.qwen_tts.model_name


def get_qwen_tts_model_path(model_name: QwenTTSModelName, settings: XnneHangLabSettings | None = None) -> str:
    qwen_tts_settings = (settings or _get_qwen_tts_settings()).agent.qwen_tts
    if model_name == "0.6b":
        return qwen_tts_settings.model_0_6b_path
    return qwen_tts_settings.model_1_7b_path


def _resolve_model_source(model_name: QwenTTSModelName, settings: XnneHangLabSettings) -> str:
    configured_path = get_qwen_tts_model_path(model_name, settings).strip()
    if configured_path:
        resolved_path = Path(configured_path)
        if not resolved_path.is_absolute():
            resolved_path = Path(settings.root.root_dir) / resolved_path
        if not resolved_path.exists():
            raise FileNotFoundError(f"Qwen-TTS model path does not exist for model '{model_name}': {resolved_path}")
        return str(resolved_path.resolve())

    legacy_env_model = os.environ.get("XNNEHANG_QWEN_TTS_MODEL", "").strip()
    if legacy_env_model:
        return legacy_env_model

    return DEFAULT_MODEL_SOURCES[model_name]


def _resolve_device(settings: XnneHangLabSettings | None = None) -> str:
    if device := os.environ.get("XNNEHANG_QWEN_TTS_DEVICE", "").strip():
        return device
    if settings is not None and settings.agent.qwen_tts.device.strip():
        return settings.agent.qwen_tts.device.strip()

    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _release_engine() -> None:
    global _qwen_tts_engine, _loaded_model_name, _loaded_model_source

    _voice_prompt_cache.clear()
    old_engine = _qwen_tts_engine
    _qwen_tts_engine = None
    _loaded_model_name = None
    _loaded_model_source = None
    if old_engine is not None:
        del old_engine

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            ipc_collect = getattr(torch.cuda, "ipc_collect", None)
            if callable(ipc_collect):
                ipc_collect()
    except Exception:
        pass


def get_qwen_tts_status() -> dict[str, Any]:
    settings = _get_qwen_tts_settings()
    configured_model = get_configured_qwen_tts_model_name(settings)
    return {
        "loaded": _qwen_tts_engine is not None,
        "configured_model": configured_model,
        "loaded_model": _loaded_model_name,
        "loaded_model_matches_config": _qwen_tts_engine is not None and _loaded_model_name == configured_model,
        "loaded_model_source": _loaded_model_source,
        "sample_rate": _sample_rate,
        "device": _resolve_device(settings),
    }


def load_qwen_tts_model(
    model_name: QwenTTSModelName | None = None,
    *,
    force_reload: bool = False,
) -> dict[str, Any]:
    global _qwen_tts_engine, _loaded_model_name, _loaded_model_source, _sample_rate

    settings = _get_qwen_tts_settings()
    if settings.agent.tts.provider != "qwen_tts":
        raise RuntimeError("Qwen-TTS is disabled in lab.toml")

    target_model = model_name or get_configured_qwen_tts_model_name(settings)

    with _model_lock:
        if _qwen_tts_engine is not None and _loaded_model_name == target_model and not force_reload:
            return get_qwen_tts_status()
        if _qwen_tts_engine is not None:
            _tts_logger.info(
                f"releasing qwen-tts engine before loading model={target_model} (current={_loaded_model_name})"
            )
            _release_engine()

        try:
            from faster_qwen3_tts import FasterQwen3TTS
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("faster-qwen3-tts is not installed") from exc

        model_source = _resolve_model_source(target_model, settings)
        device = _resolve_device(settings)
        _tts_logger.info(f"qwen-tts load start: model={target_model}, source={model_source}, device={device}")

        kwargs: dict[str, Any] = {"device": device}
        if device == "cuda":
            try:
                import torch

                kwargs["dtype"] = torch.bfloat16
            except Exception:
                pass

        _qwen_tts_engine = FasterQwen3TTS.from_pretrained(model_source, **kwargs)

        warmup_fn = getattr(_qwen_tts_engine, "_warmup", None)
        if settings.agent.qwen_tts.warmup_cuda_graphs and device == "cuda" and callable(warmup_fn):
            try:
                _tts_logger.info("warming up qwen-tts model (cuda graphs)...")
                warmup_fn(prefill_len=100)
                _tts_logger.info("qwen-tts warmup done")
            except Exception:
                _tts_logger.warning("qwen-tts warmup failed, continue without warmup")

        try:
            _warmup_qwen_voice_references(_qwen_tts_engine, settings)
        except Exception:
            _release_engine()
            raise

        _sample_rate = DEFAULT_SAMPLE_RATE
        _loaded_model_name = target_model
        _loaded_model_source = model_source
        _tts_logger.info(f"qwen-tts load complete: model={target_model}, sample_rate={_sample_rate}")

    return get_qwen_tts_status()


def init_qwen_tts_model() -> None:
    load_qwen_tts_model()


def reload_qwen_tts_model(model_name: QwenTTSModelName | None = None) -> dict[str, Any]:
    return load_qwen_tts_model(model_name=model_name, force_reload=True)


def get_qwen_tts_model() -> Any:
    settings = _get_qwen_tts_settings()
    if settings.agent.tts.provider != "qwen_tts":
        raise HTTPException(status_code=503, detail="Qwen-TTS is disabled in lab.toml")

    configured_model = get_configured_qwen_tts_model_name(settings)
    if _qwen_tts_engine is None:
        raise HTTPException(
            status_code=503,
            detail=f"Qwen-TTS model '{configured_model}' is not loaded. Call /tts/qwen-tts/load first.",
        )

    if _loaded_model_name != configured_model:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Configured Qwen-TTS model '{configured_model}' is not loaded. "
                f"Currently loaded model: '{_loaded_model_name}'. "
                "Call /tts/qwen-tts/load or /tts/qwen-tts/reload."
            ),
        )

    return _qwen_tts_engine


def get_sample_rate() -> int:
    return _sample_rate


def _as_float32_mono_array(value: Any) -> Float32Array:
    arr = np.asarray(value, dtype=np.float32).squeeze()
    return arr


def _empty_float32() -> Float32Array:
    return np.zeros(0, dtype=np.float32)


def _to_wav_chunk(pcm: Float32Array, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, pcm, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _to_wav_b64(pcm: Float32Array, sample_rate: int) -> str:
    wav_bytes = _to_wav_chunk(pcm, sample_rate)
    return base64.b64encode(wav_bytes).decode("utf-8")


def _concat_audio(audio_list: Any) -> Float32Array:
    if isinstance(audio_list, np.ndarray):
        return _as_float32_mono_array(audio_list)

    parts: list[Float32Array] = []
    try:
        for chunk in audio_list:
            arr = _as_float32_mono_array(chunk)
            if arr.size > 0:
                parts.append(arr)
    except TypeError:
        arr = _as_float32_mono_array(audio_list)
        if arr.size > 0:
            parts.append(arr)

    if not parts:
        return _empty_float32()

    return np.concatenate(parts)


def _to_wav_bytes(pcm: Float32Array, sample_rate: int) -> bytes:
    return _to_wav_chunk(pcm, sample_rate)


def _voice_prompt_key(ref_audio: Path | None, ref_text: str) -> tuple[bytes, str]:
    if ref_audio is None:
        raise HTTPException(status_code=400, detail="ref_audio is required")
    if not ref_audio.is_file():
        raise HTTPException(status_code=404, detail="Reference audio file not found")
    if not ref_text:
        raise HTTPException(status_code=400, detail="ref_text is required")
    with ref_audio.open("rb") as audio_file:
        return hashlib.file_digest(audio_file, "sha256").digest(), ref_text


def _get_voice_clone_prompt(model: Any, ref_audio: Path | None, ref_text: str) -> Any:
    """Called under _model_lock; local references and uploads share content keys."""
    key = _voice_prompt_key(ref_audio, ref_text)
    if key not in _voice_prompt_cache:
        # Preserve faster-qwen3-tts's default trailing silence for ICL cloning.
        audio = model._load_ref_audio_with_silence(ref_audio)
        prompt = model.model.create_voice_clone_prompt(ref_audio=audio, ref_text=ref_text)
        _voice_prompt_cache[key] = prompt
        if len(_voice_prompt_cache) > _MAX_CACHED_VOICE_PROMPTS:
            _voice_prompt_cache.popitem(last=False)
    _voice_prompt_cache.move_to_end(key)
    return _voice_prompt_cache[key]


def _warmup_qwen_voice_references(model: Any, settings: XnneHangLabSettings) -> None:
    """Called under _model_lock, before marking the loaded engine ready."""
    profile_path = settings.agent.memory_agent_profile
    if not profile_path:
        return  # Standalone API mode has no configured voice to prewarm.
    profile = Profile.from_toml(Path(settings.root.root_dir) / profile_path)
    voice_id = (profile.character.tts.voice or "").strip() if profile.character is not None else ""
    if not voice_id:
        return

    started = time.perf_counter()
    references: dict[tuple[bytes, str], Path] = {}
    for audio, text, _speaker in resolve_all_voice_assets(settings, voice_id):
        references[_voice_prompt_key(audio, (text or "").strip())] = audio
    default_audio, default_text, _speaker = resolve_voice_assets(settings, voice_id)
    default_text = (default_text or "").strip()
    default_key = _voice_prompt_key(default_audio, default_text)
    references[default_key] = default_audio
    if len(references) > _MAX_CACHED_VOICE_PROMPTS:
        raise ValueError(
            f"Qwen-TTS voice '{voice_id}' has {len(references)} references, but cache capacity is "
            f"{_MAX_CACHED_VOICE_PROMPTS}. Select fewer voice clips before startup."
        )
    keys = list(references)
    audios = [model._load_ref_audio_with_silence(references[key]) for key in keys]
    prompts = model.model.create_voice_clone_prompt(ref_audio=audios, ref_text=[key[1] for key in keys])
    if len(prompts) != len(keys):
        raise RuntimeError("Qwen-TTS batch prompt count does not match reference count")
    _voice_prompt_cache.update((key, [prompt]) for key, prompt in zip(keys, prompts, strict=True))
    _tts_logger.info(
        f"qwen-tts reference warmup complete: voice={voice_id}, prompts={len(keys)}, "
        f"elapsed={time.perf_counter() - started:.2f}s"
    )

    started = time.perf_counter()
    audio_arrays, _sample_rate = model.generate_voice_clone(
        text="今天过得怎么样？要不要一起出去走走？",
        language="Auto",
        voice_clone_prompt=_voice_prompt_cache[default_key],
        ref_text=default_text,
    )
    if _concat_audio(audio_arrays).size == 0:
        raise RuntimeError("Qwen-TTS synthesis warmup returned no audio")
    _tts_logger.info(f"qwen-tts synthesis warmup complete: elapsed={time.perf_counter() - started:.2f}s")


def synthesize_once(*, text: str, ref_audio: Path | None, ref_text: str | None) -> bytes:
    ref_text_str = (ref_text or "").strip()

    with _model_lock:
        model = get_qwen_tts_model()
        prompt = _get_voice_clone_prompt(model, ref_audio, ref_text_str)
        result: Any = model.generate_voice_clone(
            text=text,
            language="Auto",
            voice_clone_prompt=prompt,
            ref_text=ref_text_str,
        )

    audio_arrays, sample_rate = cast("tuple[Any, Any]", result)

    audio = _concat_audio(audio_arrays)
    if audio.size == 0:
        audio = np.zeros(1, dtype=np.float32)

    sr = int(sample_rate) if isinstance(sample_rate, (int, float)) else get_sample_rate()
    return _to_wav_bytes(audio, sr)


async def synthesize_stream(
    *,
    text: str,
    ref_audio: Path | None,
    ref_text: str | None,
    chunk_size: int = 8,
) -> AsyncIterator[str]:
    ref_text_str = (ref_text or "").strip()

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
                model = get_qwen_tts_model()
                prompt = _get_voice_clone_prompt(model, ref_audio, ref_text_str)
                gen: Any = model.generate_voice_clone_streaming(
                    text=text,
                    language="Auto",
                    voice_clone_prompt=prompt,
                    ref_text=ref_text_str,
                    chunk_size=chunk_size,
                    non_streaming_mode=False,
                )

                first_audio: Any = next(gen, None)
                if first_audio is not None:
                    first_audio_tuple = cast("tuple[Any, Any, Any]", first_audio)
                    raw_audio_chunk, sr_raw, timing_raw = first_audio_tuple

                    sr = int(sr_raw) if isinstance(sr_raw, (int, float)) else get_sample_rate()
                    timing = cast("dict[str, Any]", timing_raw)

                    wall_first_ms = (time.perf_counter() - t0) * 1000.0
                    model_ms = float(timing.get("prefill_ms", 0.0)) + float(timing.get("decode_ms", 0.0))
                    voice_clone_ms = max(0.0, wall_first_ms - model_ms)

                    total_gen_ms += model_ms
                    if ttfa_ms is None:
                        ttfa_ms = total_gen_ms

                    audio_chunk = _concat_audio(raw_audio_chunk)
                    if audio_chunk.size > 0:
                        dur = audio_chunk.shape[0] / sr
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

                for item in gen:
                    audio_tuple = cast("tuple[Any, Any, Any]", item)
                    raw_audio_chunk, sr_raw, timing_raw = audio_tuple

                    sr = int(sr_raw) if isinstance(sr_raw, (int, float)) else get_sample_rate()
                    timing = cast("dict[str, Any]", timing_raw)

                    total_gen_ms += float(timing.get("prefill_ms", 0.0)) + float(timing.get("decode_ms", 0.0))
                    if ttfa_ms is None:
                        ttfa_ms = total_gen_ms

                    audio_chunk = _concat_audio(raw_audio_chunk)
                    if audio_chunk.size == 0:
                        continue

                    dur = audio_chunk.shape[0] / sr
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

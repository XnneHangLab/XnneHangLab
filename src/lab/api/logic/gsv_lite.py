from __future__ import annotations

import gc
import io
import json
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import soundfile as sf
from fastapi import HTTPException
from loguru import logger

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.profile.schema import Profile

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from numpy.typing import NDArray

DEFAULT_SAMPLE_RATE = 32000
_GSV_LITE_GPT_CACHE = [(1, 512), (1, 1024), (1, 2048), (4, 512), (4, 1024)]
_GSV_LITE_SEGMENT_MAX_CHARS = 80
_GSV_LITE_SEGMENT_SILENCE_S = 0.08
_JAPANESE_CHAR_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uff66-\uff9f]")
_gsv_lite_monkey_patch_applied = False

_tts_logger = logger.bind(group="tts")
_gsv_lite_engine: Any | None = None
_loaded_model_spec: GSVLiteModelSpec | None = None
_model_lock = threading.Lock()


@dataclass(frozen=True)
class GSVLiteModelSpec:
    character_name: str
    character_dir: Path
    gpt_path: Path
    sovits_path: Path
    models_dir: Path


def _get_gsv_lite_settings() -> XnneHangLabSettings:
    return load_settings_file("lab.toml", XnneHangLabSettings)


def _resolve_profile_path(settings: XnneHangLabSettings, profile_path_str: str) -> Path:
    profile_path = Path(profile_path_str)
    if not profile_path.is_absolute():
        profile_path = Path(settings.root.root_dir) / profile_path
    return profile_path


def _resolve_active_profile(settings: XnneHangLabSettings) -> Profile:
    profile_path_str = settings.agent.memory_agent_profile
    if not profile_path_str:
        raise RuntimeError("memory_agent_profile is not configured")

    profile_path = _resolve_profile_path(settings, profile_path_str)
    if not profile_path.exists():
        raise FileNotFoundError(f"memory_agent_profile not found: {profile_path}")

    return Profile.from_toml(profile_path)


def _resolve_active_character_name(settings: XnneHangLabSettings) -> str:
    profile = _resolve_active_profile(settings)
    if profile.character is None:
        raise RuntimeError("active profile does not define [character]")

    if profile.character.tts.character_name.strip():
        return profile.character.tts.character_name.strip()
    if profile.character.character_name.strip():
        return profile.character.character_name.strip()
    if profile.profile.name.strip():
        return profile.profile.name.strip()
    raise RuntimeError("failed to resolve active character name for gsv-lite")


def _resolve_character_dir(settings: XnneHangLabSettings, character_name: str) -> Path:
    return (Path(settings.root.root_dir) / "models" / "gptsovits" / character_name).resolve()


def _resolve_infer_config_path(character_dir: Path) -> Path:
    infer_config_path = character_dir / "infer_config.json"
    if infer_config_path.exists():
        return infer_config_path

    infer_json_path = character_dir / "infer.json"
    if infer_json_path.exists():
        return infer_json_path

    return infer_config_path


def _load_infer_config(character_dir: Path) -> dict[str, Any]:
    config_path = _resolve_infer_config_path(character_dir)
    if not config_path.exists():
        raise FileNotFoundError(f"infer config not found for character directory: {character_dir}")
    with config_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise RuntimeError(f"invalid infer config: {config_path}")
    return cast("dict[str, Any]", data)


def _resolve_model_file(character_dir: Path, raw_path: object, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise RuntimeError(f"{label} is missing in infer config: {character_dir}")
    resolved = (character_dir / raw_path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"{label} does not exist: {resolved}")
    return resolved


def _get_configured_model_spec(settings: XnneHangLabSettings | None = None) -> GSVLiteModelSpec:
    resolved_settings = settings or _get_gsv_lite_settings()
    character_name = _resolve_active_character_name(resolved_settings)
    character_dir = _resolve_character_dir(resolved_settings, character_name)
    if not character_dir.exists():
        raise FileNotFoundError(f"gsv-lite character directory does not exist: {character_dir}")

    infer_config = _load_infer_config(character_dir)
    gpt_path = _resolve_model_file(character_dir, infer_config.get("gpt_path"), "gpt_path")
    sovits_path = _resolve_model_file(character_dir, infer_config.get("sovits_path"), "sovits_path")
    models_dir = (Path(resolved_settings.root.root_dir) / "models").resolve()
    return GSVLiteModelSpec(
        character_name=character_name,
        character_dir=character_dir,
        gpt_path=gpt_path,
        sovits_path=sovits_path,
        models_dir=models_dir,
    )


def _resolve_warmup_reference(settings: XnneHangLabSettings, spec: GSVLiteModelSpec) -> tuple[Path | None, str | None]:
    try:
        profile = _resolve_active_profile(settings)
    except Exception:
        profile = None

    if profile is not None and profile.character is not None:
        emotions = profile.character.tts.emotions
        emotion = emotions.get("default") or next(iter(emotions.values()), None)
        if emotion is not None and emotion.path:
            ref_audio = (spec.character_dir / emotion.path).resolve()
            if ref_audio.is_file():
                ref_text = emotion.ref_text.strip() or None
                return ref_audio, ref_text

    infer_config = _load_infer_config(spec.character_dir)
    emotion_list = infer_config.get("emotion_list")
    if isinstance(emotion_list, dict):
        emotion_map = cast("dict[str, object]", emotion_list)
        for candidate in emotion_map.values():
            if not isinstance(candidate, dict):
                continue
            candidate_dict = cast("dict[str, object]", candidate)
            ref_wav_path = candidate_dict.get("ref_wav_path")
            prompt_text = candidate_dict.get("prompt_text")
            if isinstance(ref_wav_path, str) and ref_wav_path.strip():
                ref_audio = (spec.character_dir / ref_wav_path).resolve()
                if ref_audio.is_file():
                    ref_text = prompt_text.strip() if isinstance(prompt_text, str) else ""
                    return ref_audio, (ref_text or None)

    return None, None


def _release_engine() -> None:
    global _gsv_lite_engine, _loaded_model_spec

    old_engine = _gsv_lite_engine
    _gsv_lite_engine = None
    _loaded_model_spec = None
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


def _configure_gsv_lite_openjtalk(models_dir: Path) -> None:
    ja_dir = models_dir / "g2p" / "ja"
    openjtalk_dict_dir = ja_dir / "open_jtalk_dic_utf_8-1.11"
    user_dict_csv = ja_dir / "userdict.csv"
    user_dict_bin = ja_dir / "user.dict"

    if not (openjtalk_dict_dir.is_dir() or user_dict_csv.is_file() or user_dict_bin.is_file()):
        return

    if openjtalk_dict_dir.is_dir():
        os.environ["OPEN_JTALK_DICT_DIR"] = str(openjtalk_dict_dir)

    try:
        import pyopenjtalk
    except Exception as exc:
        _tts_logger.warning(f"gsv-lite failed to import pyopenjtalk for local JA resources: {exc}")
        return

    if openjtalk_dict_dir.is_dir():
        try:
            pyopenjtalk.OPEN_JTALK_DICT_DIR = str(openjtalk_dict_dir).encode("utf-8")
            unset_user_dict = getattr(pyopenjtalk, "unset_user_dict", None)
            if callable(unset_user_dict):
                unset_user_dict()
            _tts_logger.info(f"gsv-lite configured OpenJTalk dictionary: {openjtalk_dict_dir}")
        except Exception as exc:
            _tts_logger.warning(f"gsv-lite failed to activate local OpenJTalk dictionary: {exc}")

    if user_dict_csv.is_file() and not user_dict_bin.is_file():
        try:
            mecab_dict_index = cast("Any", pyopenjtalk).mecab_dict_index
            mecab_dict_index(str(user_dict_csv), str(user_dict_bin))
            _tts_logger.info(f"gsv-lite built OpenJTalk user dictionary: {user_dict_bin}")
        except Exception as exc:
            _tts_logger.warning(f"gsv-lite failed to build OpenJTalk user dictionary: {exc}")

    if user_dict_bin.is_file():
        try:
            update_user_dict = cast("Any", pyopenjtalk).update_global_jtalk_with_user_dict
            update_user_dict(str(user_dict_bin))
            _tts_logger.info(f"gsv-lite activated OpenJTalk user dictionary: {user_dict_bin}")
        except Exception as exc:
            _tts_logger.warning(f"gsv-lite failed to activate OpenJTalk user dictionary: {exc}")


def _redistribute_japanese_word2ph(words: list[str], phone_count: int) -> dict[str, list[Any]]:
    if phone_count <= 0:
        return {"word": words[:1], "ph": [0] if words else []}

    if not words:
        return {"word": ["?"], "ph": [phone_count]}

    if phone_count < len(words):
        return {"word": ["".join(words)], "ph": [phone_count]}

    base = phone_count // len(words)
    extra = phone_count % len(words)
    counts = [base + (1 if i < extra else 0) for i in range(len(words))]
    return {"word": list(words), "ph": counts}


def _repair_japanese_word2ph(word2ph: object, phone_count: int) -> dict[str, list[Any]]:
    if not isinstance(word2ph, dict):
        return _redistribute_japanese_word2ph([], phone_count)

    mapping = cast("dict[str, object]", word2ph)
    raw_words = mapping.get("word")
    raw_counts = mapping.get("ph")
    if not isinstance(raw_words, list) or not isinstance(raw_counts, list):
        return _redistribute_japanese_word2ph([], phone_count)

    word_list = cast("list[object]", raw_words)
    raw_count_list = cast("list[object]", raw_counts)
    words = [str(word) for word in word_list]
    try:
        counts = [max(int(cast("Any", count)), 0) for count in raw_count_list]
    except Exception:
        return _redistribute_japanese_word2ph(words, phone_count)

    if not words or len(words) != len(counts):
        return _redistribute_japanese_word2ph(words, phone_count)

    diff = phone_count - sum(counts)
    if diff == 0:
        return {"word": words, "ph": counts}

    indices = list(range(len(counts) - 1, -1, -1))
    if diff > 0:
        step = 0
        while diff > 0:
            counts[indices[step % len(indices)]] += 1
            diff -= 1
            step += 1
        return {"word": words, "ph": counts}

    remaining = -diff
    step = 0
    max_iterations = max(1, len(indices) * (remaining + 1))
    while remaining > 0 and step < max_iterations:
        idx = indices[step % len(indices)]
        if counts[idx] > 1:
            counts[idx] -= 1
            remaining -= 1
        step += 1

    if remaining > 0:
        return _redistribute_japanese_word2ph(words, phone_count)

    return {"word": words, "ph": counts}


def _apply_gsv_lite_monkey_patch() -> None:
    global _gsv_lite_monkey_patch_applied

    if _gsv_lite_monkey_patch_applied:
        return

    from gsv_tts.GPT_SoVITS.G2P.Japanese.japanese import JapaneseG2P

    current_g2p = cast(
        "Callable[[Any, str, bool], tuple[list[str], dict[str, list[Any]]]]",
        cast("Any", JapaneseG2P).g2p,
    )
    if getattr(cast("Any", current_g2p), "_xnnehanglab_gsv_lite_patched", False):
        _gsv_lite_monkey_patch_applied = True
        return

    original_g2p = current_g2p

    def patched_g2p(self: Any, norm_text: str, with_prosody: bool = True) -> tuple[list[str], dict[str, list[Any]]]:
        phones, word2ph = original_g2p(self, norm_text, with_prosody)

        try:
            original_total = sum(int(count) for count in word2ph["ph"])
        except Exception:
            original_total = None

        if original_total == len(phones):
            return phones, word2ph

        repaired = _repair_japanese_word2ph(word2ph, len(phones))
        repaired_total = sum(repaired["ph"])
        _tts_logger.warning(
            "gsv-lite monkey patch repaired Japanese word2ph mismatch: "
            f"text={norm_text!r}, phones={len(phones)}, original_total={original_total}, repaired_total={repaired_total}"
        )
        return phones, repaired

    cast("Any", patched_g2p)._xnnehanglab_gsv_lite_patched = True
    JapaneseG2P.g2p = patched_g2p
    _gsv_lite_monkey_patch_applied = True
    _tts_logger.info("gsv-lite monkey patch applied: JapaneseG2P.g2p word2ph repair")


def get_gsv_lite_status() -> dict[str, Any]:
    settings = _get_gsv_lite_settings()
    configured_character: str | None = None
    configured_gpt_path: str | None = None
    configured_sovits_path: str | None = None
    configured: GSVLiteModelSpec | None = None
    configured_error: str | None = None

    try:
        configured = _get_configured_model_spec(settings)
        configured_character = configured.character_name
        configured_gpt_path = str(configured.gpt_path)
        configured_sovits_path = str(configured.sovits_path)
    except Exception as exc:
        configured_error = str(exc)

    return {
        "loaded": _gsv_lite_engine is not None,
        "configured_character": configured_character,
        "loaded_character": _loaded_model_spec.character_name if _loaded_model_spec is not None else None,
        "loaded_model_matches_config": _loaded_model_spec is not None
        and configured is not None
        and _loaded_model_spec == configured,
        "configured_gpt_path": configured_gpt_path,
        "configured_sovits_path": configured_sovits_path,
        "loaded_gpt_path": str(_loaded_model_spec.gpt_path) if _loaded_model_spec is not None else None,
        "loaded_sovits_path": str(_loaded_model_spec.sovits_path) if _loaded_model_spec is not None else None,
        "models_dir": str((Path(settings.root.root_dir) / "models").resolve()),
        "sample_rate": DEFAULT_SAMPLE_RATE,
        "configured_error": configured_error,
    }


def load_gsv_lite_model(*, force_reload: bool = False) -> dict[str, Any]:
    global _gsv_lite_engine, _loaded_model_spec

    settings = _get_gsv_lite_settings()
    if not settings.package.gsv_lite:
        raise RuntimeError("GSV-Lite is disabled in lab.toml")

    target_spec = _get_configured_model_spec(settings)

    with _model_lock:
        if _gsv_lite_engine is not None and _loaded_model_spec == target_spec and not force_reload:
            return get_gsv_lite_status()
        if _gsv_lite_engine is not None:
            _tts_logger.info(
                "releasing gsv-lite engine before reload "
                f"(current_character={_loaded_model_spec.character_name if _loaded_model_spec is not None else '-'})"
            )
            _release_engine()

        _configure_gsv_lite_openjtalk(target_spec.models_dir)

        try:
            from gsv_tts import TTS
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("gsv-tts-lite is not installed") from exc
        _apply_gsv_lite_monkey_patch()

        _tts_logger.info(
            "gsv-lite load start: "
            f"character={target_spec.character_name}, gpt={target_spec.gpt_path}, "
            f"sovits={target_spec.sovits_path}, models_dir={target_spec.models_dir}"
        )

        engine = TTS(models_dir=str(target_spec.models_dir), gpt_cache=_GSV_LITE_GPT_CACHE)
        engine.load_gpt_model(str(target_spec.gpt_path))
        engine.load_sovits_model(str(target_spec.sovits_path))

        warmup_ref_audio, warmup_ref_text = _resolve_warmup_reference(settings, target_spec)
        if warmup_ref_audio is not None and warmup_ref_text:
            try:
                infer = cast("Callable[..., Any]", cast("Any", engine).infer)
                infer(
                    spk_audio_path=str(warmup_ref_audio),
                    prompt_audio_path=str(warmup_ref_audio),
                    prompt_audio_text=warmup_ref_text,
                    text="System warmup.",
                )
                _tts_logger.info(f"gsv-lite warmup finished: character={target_spec.character_name}")
            except Exception:
                _tts_logger.warning("gsv-lite warmup failed; continue with loaded engine")

        _gsv_lite_engine = engine
        _loaded_model_spec = target_spec
        _tts_logger.info(f"gsv-lite load complete: character={target_spec.character_name}")

    return get_gsv_lite_status()


def reload_gsv_lite_model() -> dict[str, Any]:
    return load_gsv_lite_model(force_reload=True)


def get_gsv_lite_model() -> Any:
    settings = _get_gsv_lite_settings()
    if not settings.package.gsv_lite:
        raise HTTPException(status_code=503, detail="GSV-Lite is disabled in lab.toml")

    configured = _get_configured_model_spec(settings)
    if _gsv_lite_engine is None or _loaded_model_spec is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"GSV-Lite model '{configured.character_name}' is not initialized. "
                "It should be loaded during application startup."
            ),
        )

    if _loaded_model_spec != configured:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Configured GSV-Lite character '{configured.character_name}' does not match the loaded character. "
                f"Currently loaded character: '{_loaded_model_spec.character_name}'. "
                "Restart the service to apply the new profile/model selection."
            ),
        )

    return _gsv_lite_engine


def get_sample_rate() -> int:
    return DEFAULT_SAMPLE_RATE


def _should_retry_gsv_lite_text(exc: Exception, text: str) -> bool:
    return (
        isinstance(exc, AssertionError) and "length mismatch" in str(exc) and _JAPANESE_CHAR_RE.search(text) is not None
    )


def _normalize_gsv_lite_retry_text(text: str) -> str:
    normalized = text.strip()
    normalized = normalized.replace("......", "…").replace("...", "…")
    normalized = normalized.translate(str.maketrans({"?": "？", "!": "！"}))

    # Rare/literary kanji occasionally break the Japanese G2P alignment in gsv-tts-lite.
    replacement_rules = (
        ("洒れる", "こぼれる"),
        ("洒れた", "こぼれた"),
        ("洒れて", "こぼれて"),
        ("洒れ", "こぼれ"),
    )
    for source, target in replacement_rules:
        normalized = normalized.replace(source, target)

    return normalized


def _should_retry_gsv_lite_by_chunking(exc: Exception, text: str) -> bool:
    message = str(exc)
    return (
        isinstance(exc, RuntimeError)
        and "expanded size of the tensor" in message
        and "existing size" in message
        and len(text.strip()) > _GSV_LITE_SEGMENT_MAX_CHARS
    )


def _split_gsv_lite_long_text(text: str, *, max_chars: int = _GSV_LITE_SEGMENT_MAX_CHARS) -> list[str]:
    normalized = "".join(text.split())
    if len(normalized) <= max_chars:
        return [normalized]

    primary_parts = [part for part in re.split(r"(?<=[。！？!?…])", normalized) if part]
    parts = (
        primary_parts if len(primary_parts) > 1 else [part for part in re.split(r"(?<=[、，,])", normalized) if part]
    )
    if not parts:
        parts = [normalized]

    segments: list[str] = []
    current = ""

    def flush_segment(value: str) -> None:
        stripped = value.strip()
        if stripped:
            segments.append(stripped)

    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue

        if len(chunk) > max_chars:
            if current:
                flush_segment(current)
                current = ""

            remaining = chunk
            while len(remaining) > max_chars:
                split_at = max(
                    remaining.rfind("。", 0, max_chars),
                    remaining.rfind("！", 0, max_chars),
                    remaining.rfind("？", 0, max_chars),
                    remaining.rfind("、", 0, max_chars),
                    remaining.rfind("，", 0, max_chars),
                    remaining.rfind(",", 0, max_chars),
                )
                if split_at <= 0:
                    split_at = max_chars
                else:
                    split_at += 1
                flush_segment(remaining[:split_at])
                remaining = remaining[split_at:].strip()
            current = remaining
            continue

        candidate = f"{current}{chunk}"
        if current and len(candidate) > max_chars:
            flush_segment(current)
            current = chunk
        else:
            current = candidate

    if current:
        flush_segment(current)

    return segments or [normalized]


def _wav_bytes_from_audio(audio_data: NDArray[np.float32], samplerate: int) -> bytes:
    buf = io.BytesIO()
    sf_write = cast("Callable[..., None]", cast("Any", sf).write)
    sf_write(buf, audio_data, samplerate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _wav_bytes_from_clips(clips: list[Any], *, silence_s: float = _GSV_LITE_SEGMENT_SILENCE_S) -> bytes:
    if not clips:
        raise RuntimeError("gsv-lite clip list is empty")

    samplerate = int(clips[0].samplerate)
    arrays: list[NDArray[np.float32]] = []
    silence_samples = max(int(samplerate * silence_s), 0)
    silence = np.zeros(silence_samples, dtype=np.float32) if silence_samples else None

    for i, clip in enumerate(clips):
        clip_samplerate = int(clip.samplerate)
        if clip_samplerate != samplerate:
            raise RuntimeError(f"gsv-lite clip samplerate mismatch: expected {samplerate}, got {clip_samplerate}")
        audio_array = np.asarray(clip.audio_data, dtype=np.float32)
        arrays.append(audio_array)
        if silence is not None and i < len(clips) - 1:
            arrays.append(silence)

    merged_audio = np.concatenate(arrays, axis=0).astype(np.float32, copy=False) if len(arrays) > 1 else arrays[0]
    return _wav_bytes_from_audio(merged_audio, samplerate)


async def _infer_clip(
    model: Any,
    *,
    text: str,
    speaker_audio_path: Path,
    ref_audio: Path,
    prompt_text: str,
    top_k: int,
    top_p: float,
    temperature: float,
    repetition_penalty: float,
    noise_scale: float,
    speed: float,
) -> Any:
    infer_async = cast("Callable[..., Awaitable[Any]]", model.infer_async)
    return await infer_async(
        spk_audio_path=str(speaker_audio_path),
        prompt_audio_path=str(ref_audio),
        prompt_audio_text=prompt_text,
        text=text,
        top_k=top_k,
        top_p=top_p,
        temperature=temperature,
        repetition_penalty=repetition_penalty,
        noise_scale=noise_scale,
        speed=speed,
    )


async def synthesize_once(
    *,
    text: str,
    ref_audio: Path | None,
    ref_text: str | None,
    speaker_audio: Path | None = None,
    top_k: int = 15,
    top_p: float = 1.0,
    temperature: float = 1.0,
    repetition_penalty: float = 1.35,
    noise_scale: float = 0.5,
    speed: float = 1.0,
) -> bytes:
    model = get_gsv_lite_model()

    if ref_audio is None:
        raise HTTPException(status_code=400, detail="ref_audio_path is required")
    if not ref_audio.exists():
        raise HTTPException(status_code=404, detail=f"ref_audio_path not found: {ref_audio}")

    prompt_text = (ref_text or "").strip()
    if not prompt_text:
        raise HTTPException(status_code=400, detail="ref_text is required for gsv-lite")

    speaker_audio_path = speaker_audio or ref_audio
    if not speaker_audio_path.exists():
        raise HTTPException(status_code=404, detail=f"speaker_audio_path not found: {speaker_audio_path}")

    candidate_text = text

    try:
        clip: Any = await _infer_clip(
            model,
            text=candidate_text,
            speaker_audio_path=speaker_audio_path,
            ref_audio=ref_audio,
            prompt_text=prompt_text,
            top_k=top_k,
            top_p=top_p,
            temperature=temperature,
            repetition_penalty=repetition_penalty,
            noise_scale=noise_scale,
            speed=speed,
        )
    except Exception as exc:
        last_exc = exc
        if _should_retry_gsv_lite_text(exc, candidate_text):
            normalized_text = _normalize_gsv_lite_retry_text(candidate_text)
            if normalized_text != candidate_text:
                _tts_logger.warning(
                    "gsv-lite retry after Japanese G2P mismatch: "
                    f"original_text={candidate_text!r}, normalized_text={normalized_text!r}"
                )
                candidate_text = normalized_text
                try:
                    clip = await _infer_clip(
                        model,
                        text=candidate_text,
                        speaker_audio_path=speaker_audio_path,
                        ref_audio=ref_audio,
                        prompt_text=prompt_text,
                        top_k=top_k,
                        top_p=top_p,
                        temperature=temperature,
                        repetition_penalty=repetition_penalty,
                        noise_scale=noise_scale,
                        speed=speed,
                    )
                except Exception as retry_exc:
                    last_exc = retry_exc
                else:
                    return _wav_bytes_from_clips([clip])

        if _should_retry_gsv_lite_by_chunking(last_exc, candidate_text):
            chunks = _split_gsv_lite_long_text(candidate_text)
            if len(chunks) > 1:
                _tts_logger.warning(
                    "gsv-lite retry by splitting long text after GPT cache overflow: "
                    f"text_len={len(candidate_text)}, chunks={len(chunks)}"
                )
                clips: list[Any] = []
                for chunk in chunks:
                    clips.append(
                        await _infer_clip(
                            model,
                            text=chunk,
                            speaker_audio_path=speaker_audio_path,
                            ref_audio=ref_audio,
                            prompt_text=prompt_text,
                            top_k=top_k,
                            top_p=top_p,
                            temperature=temperature,
                            repetition_penalty=repetition_penalty,
                            noise_scale=noise_scale,
                            speed=speed,
                        )
                    )
                return _wav_bytes_from_clips(clips)

        raise last_exc from None

    return _wav_bytes_from_clips([clip])

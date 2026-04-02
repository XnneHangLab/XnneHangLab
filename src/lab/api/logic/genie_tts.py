from __future__ import annotations

import asyncio
import gc
import importlib
import io
import json
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import soundfile as sf
from fastapi import HTTPException
from loguru import logger

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.profile.schema import Profile

DEFAULT_SAMPLE_RATE = 32000
_GENIE_TTS_MODEL_DIRNAME = "genie-tts"
_GENIE_DATA_DIRNAME = "geniedata"
_LEGACY_GENIE_DATA_DIRNAME = "GenieData"
_GPT_SOVITS_MODEL_DIRNAME = "gptsovits"
_GENIE_TTS_MODEL_DIR_KEYS = ("genie_model_dir", "genie_tts_path", "onnx_model_dir", "tts_models_dir")
_GENIE_TTS_MODEL_DIR_CANDIDATES = ("tts_models", "genie_tts", "genie", "onnx")
_GENIE_TTS_ROOT_MODEL_MARKERS = (
    "vits_fp32.onnx",
    "t2s_encoder_fp32.onnx",
    "t2s_stage_decoder_fp32.onnx",
    "t2s_first_stage_decoder_fp32.onnx",
    "prompt_encoder_fp32.onnx",
)
_GENIE_TTS_HUBERT_ONNX = "chinese-hubert-base.onnx"
_GENIE_TTS_HUBERT_FP16 = "chinese-hubert-base_weights_fp16.bin"

_tts_logger = logger.bind(group="tts")
_genie_tts_module: Any | None = None
_loaded_model_spec: GenieTTSModelSpec | None = None
_model_lock = threading.Lock()


@dataclass(frozen=True)
class GenieTTSModelSpec:
    character_name: str
    character_dir: Path
    onnx_model_dir: Path
    language: str
    use_roberta: bool


@dataclass(frozen=True)
class GenieTTSResourcePaths:
    genie_data_dir: Path
    english_g2p_dir: Path
    chinese_g2p_dir: Path
    hubert_model_dir: Path
    hubert_onnx_path: Path
    hubert_fp16_weights_path: Path
    sv_model_path: Path
    roberta_model_dir: Path
    roberta_model_path: Path
    roberta_tokenizer_path: Path


def _get_genie_tts_settings() -> XnneHangLabSettings:
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
    raise RuntimeError("failed to resolve active character name for genie-tts")


def _iter_reference_base_dirs(settings: XnneHangLabSettings, character_name: str) -> list[Path]:
    models_dir = (Path(settings.root.root_dir) / "models").resolve()
    bases: list[Path] = []
    for base in (
        (models_dir / _GENIE_TTS_MODEL_DIRNAME / character_name).resolve(),
        (models_dir / _GPT_SOVITS_MODEL_DIRNAME / character_name).resolve(),
    ):
        if base not in bases:
            bases.append(base)
    return bases


def _resolve_character_dir(settings: XnneHangLabSettings, character_name: str) -> Path:
    models_dir = (Path(settings.root.root_dir) / "models").resolve()
    preferred = (models_dir / _GENIE_TTS_MODEL_DIRNAME / character_name).resolve()
    if preferred.exists():
        return preferred

    legacy = (models_dir / _GPT_SOVITS_MODEL_DIRNAME / character_name).resolve()
    if legacy.exists():
        return legacy
    return preferred


def _resolve_genie_tts_submodule_src_dir(settings: XnneHangLabSettings) -> Path:
    return (Path(settings.root.root_dir) / "packages" / "Genie-TTS" / "src").resolve()


def _resolve_genie_data_dir(settings: XnneHangLabSettings) -> Path:
    models_dir = (Path(settings.root.root_dir) / "models").resolve()
    preferred = (models_dir / _GENIE_DATA_DIRNAME).resolve()
    if preferred.exists():
        return preferred

    legacy = (models_dir / _LEGACY_GENIE_DATA_DIRNAME).resolve()
    if legacy.exists():
        return legacy

    return preferred


def _resolve_roberta_model_dir(genie_data_dir: Path) -> Path:
    for dirname in ("roberta-wwm-ext-large-onnx", "RoBERTa"):
        candidate = (genie_data_dir / dirname).resolve()
        if candidate.is_dir():
            return candidate

    if genie_data_dir.is_dir():
        candidates = sorted(
            entry.resolve() for entry in genie_data_dir.iterdir() if entry.is_dir() and "roberta" in entry.name.lower()
        )
        if candidates:
            return candidates[0]

    return (genie_data_dir / "roberta-wwm-ext-large-onnx").resolve()


def _resolve_roberta_model_path(roberta_model_dir: Path) -> Path:
    for filename in ("RoBERTa.onnx", "model.onnx", "model_fp16.onnx"):
        candidate = (roberta_model_dir / filename).resolve()
        if candidate.is_file():
            return candidate

    if roberta_model_dir.is_dir():
        onnx_candidates = sorted(entry.resolve() for entry in roberta_model_dir.glob("*.onnx"))
        if onnx_candidates:
            return onnx_candidates[0]

    return (roberta_model_dir / "model.onnx").resolve()


def _resolve_roberta_tokenizer_path(roberta_model_dir: Path) -> Path:
    for relative_path in ("roberta_tokenizer/tokenizer.json", "tokenizer.json"):
        candidate = (roberta_model_dir / relative_path).resolve()
        if candidate.is_file():
            return candidate
    return (roberta_model_dir / "tokenizer.json").resolve()


def _resolve_genie_tts_resource_paths(settings: XnneHangLabSettings) -> GenieTTSResourcePaths:
    genie_data_dir = _resolve_genie_data_dir(settings)
    roberta_model_dir = _resolve_roberta_model_dir(genie_data_dir)
    return GenieTTSResourcePaths(
        genie_data_dir=genie_data_dir,
        english_g2p_dir=(genie_data_dir / "G2P" / "EnglishG2P").resolve(),
        chinese_g2p_dir=(genie_data_dir / "G2P" / "ChineseG2P").resolve(),
        hubert_model_dir=(genie_data_dir / "chinese-hubert-base").resolve(),
        hubert_onnx_path=(genie_data_dir / "chinese-hubert-base" / _GENIE_TTS_HUBERT_ONNX).resolve(),
        hubert_fp16_weights_path=(genie_data_dir / "chinese-hubert-base" / _GENIE_TTS_HUBERT_FP16).resolve(),
        sv_model_path=(genie_data_dir / "speaker_encoder.onnx").resolve(),
        roberta_model_dir=roberta_model_dir,
        roberta_model_path=_resolve_roberta_model_path(roberta_model_dir),
        roberta_tokenizer_path=_resolve_roberta_tokenizer_path(roberta_model_dir),
    )


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
        return {}
    with config_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise RuntimeError(f"invalid infer config: {config_path}")
    return cast("dict[str, Any]", data)


def _resolve_model_dir_from_infer_config(character_dir: Path, infer_config: dict[str, Any]) -> Path | None:
    for key in _GENIE_TTS_MODEL_DIR_KEYS:
        raw_path = infer_config.get(key)
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        resolved = (character_dir / raw_path).resolve()
        if resolved.is_dir():
            return resolved
        raise FileNotFoundError(f"{key} does not exist or is not a directory: {resolved}")
    return None


def _looks_like_genie_tts_model_dir(candidate: Path) -> bool:
    if not candidate.is_dir():
        return False
    return any((candidate / marker).is_file() for marker in _GENIE_TTS_ROOT_MODEL_MARKERS)


def _resolve_default_model_dir(character_dir: Path) -> Path | None:
    if _looks_like_genie_tts_model_dir(character_dir):
        return character_dir.resolve()

    for name in _GENIE_TTS_MODEL_DIR_CANDIDATES:
        candidate = (character_dir / name).resolve()
        if candidate.is_dir():
            return candidate
    return None


def _resolve_language(infer_config: dict[str, Any], settings: XnneHangLabSettings) -> str:
    configured_language = settings.agent.tts.genie_tts.language.strip()
    if configured_language:
        return configured_language

    raw_language = infer_config.get("language")
    if isinstance(raw_language, str) and raw_language.strip():
        return raw_language.strip()
    return "auto"


def _resolve_warmup_ref_audio_and_text(
    settings: XnneHangLabSettings,
    character_name: str,
) -> tuple[Path, str]:
    profile = _resolve_active_profile(settings)
    if profile.character is None:
        raise RuntimeError("active profile does not define [character]")

    emotions = profile.character.tts.emotions
    if not emotions:
        raise RuntimeError(f"genie-tts warmup failed: no TTS emotions configured for character '{character_name}'")

    keys_to_try: list[str] = []
    if "default" in emotions:
        keys_to_try.append("default")
    for key in emotions:
        if key not in keys_to_try:
            keys_to_try.append(key)

    checked_paths: list[Path] = []
    for key in keys_to_try:
        emotion = emotions[key]
        if not emotion.path.strip():
            continue
        ref_text = emotion.ref_text.strip()
        if not ref_text:
            continue
        for base in _iter_reference_base_dirs(settings, character_name):
            candidate = (base / emotion.path).resolve()
            checked_paths.append(candidate)
            if candidate.is_file():
                return candidate, ref_text

    if checked_paths:
        checked = ", ".join(str(path) for path in checked_paths)
        raise FileNotFoundError(
            f"genie-tts warmup failed: no configured ref audio file exists for character '{character_name}'. "
            f"Checked: {checked}"
        )

    raise RuntimeError(
        f"genie-tts warmup failed: no emotion with both path and ref_text is configured for character '{character_name}'"
    )


def _get_genie_tts_use_roberta(settings: object) -> bool:
    if not isinstance(settings, XnneHangLabSettings):
        try:
            return bool(cast("Any", settings).agent.tts.genie_tts.use_roberta)
        except AttributeError:
            return False
    return settings.agent.tts.genie_tts.use_roberta


def _get_configured_model_spec(settings: XnneHangLabSettings | None = None) -> GenieTTSModelSpec:
    resolved_settings = settings or _get_genie_tts_settings()
    character_name = _resolve_active_character_name(resolved_settings)
    character_dir = _resolve_character_dir(resolved_settings, character_name)
    if not character_dir.exists():
        raise FileNotFoundError(f"genie-tts character directory does not exist: {character_dir}")

    infer_config = _load_infer_config(character_dir)
    onnx_model_dir = _resolve_model_dir_from_infer_config(character_dir, infer_config)
    if onnx_model_dir is None:
        onnx_model_dir = _resolve_default_model_dir(character_dir)
    if onnx_model_dir is None:
        raise FileNotFoundError(
            "genie-tts ONNX model directory not found. "
            f"Checked infer config keys={list(_GENIE_TTS_MODEL_DIR_KEYS)} and default directories={list(_GENIE_TTS_MODEL_DIR_CANDIDATES)} "
            f"plus the character root itself under {character_dir}"
        )

    return GenieTTSModelSpec(
        character_name=character_name,
        character_dir=character_dir,
        onnx_model_dir=onnx_model_dir,
        language=_resolve_language(infer_config, resolved_settings),
        use_roberta=_get_genie_tts_use_roberta(resolved_settings),
    )


def _release_engine() -> None:
    global _genie_tts_module, _loaded_model_spec

    old_module = _genie_tts_module
    _genie_tts_module = None
    _loaded_model_spec = None
    if old_module is not None:
        try:
            stop = getattr(old_module, "stop", None)
            if callable(stop):
                stop()
        except Exception:
            pass
        del old_module

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


@asynccontextmanager
async def _hold_model_lock_async():
    await asyncio.to_thread(_model_lock.acquire)
    try:
        yield
    finally:
        _model_lock.release()


def _requires_english_g2p(language: str) -> bool:
    normalized = language.strip().lower()
    return normalized in {"english", "hybrid-chinese-english", "auto"}


def _requires_chinese_g2p(language: str) -> bool:
    normalized = language.strip().lower()
    return normalized in {"chinese", "hybrid-chinese-english", "auto"}


def _requires_speaker_encoder(spec: GenieTTSModelSpec) -> bool:
    return (spec.onnx_model_dir / "prompt_encoder_fp32.onnx").is_file()


def _validate_genie_tts_resources(settings: XnneHangLabSettings, spec: GenieTTSModelSpec) -> GenieTTSResourcePaths:
    resources = _resolve_genie_tts_resource_paths(settings)
    missing: list[str] = []

    if _requires_english_g2p(spec.language) and not resources.english_g2p_dir.is_dir():
        missing.append(f"English G2P directory: {resources.english_g2p_dir}")
    if _requires_chinese_g2p(spec.language) and not resources.chinese_g2p_dir.is_dir():
        missing.append(f"Chinese G2P directory: {resources.chinese_g2p_dir}")
    if not resources.hubert_onnx_path.is_file():
        missing.append(f"Chinese HuBERT ONNX: {resources.hubert_onnx_path}")
    if not resources.hubert_fp16_weights_path.is_file():
        missing.append(f"Chinese HuBERT FP16 weights: {resources.hubert_fp16_weights_path}")
    if _requires_speaker_encoder(spec) and not resources.sv_model_path.is_file():
        missing.append(f"speaker encoder ONNX: {resources.sv_model_path}")
    if spec.use_roberta and not resources.roberta_model_path.is_file():
        missing.append(f"RoBERTa ONNX: {resources.roberta_model_path}")
    if spec.use_roberta and not resources.roberta_tokenizer_path.is_file():
        missing.append(f"RoBERTa tokenizer: {resources.roberta_tokenizer_path}")

    if missing:
        raise FileNotFoundError(
            "Genie-TTS resources are not installed in XnneHangLab models/.\n"
            "Automatic download is disabled here.\n" + "\n".join(f"- {item}" for item in missing)
        )

    return resources


def _configure_genie_tts_environment(settings: XnneHangLabSettings, spec: GenieTTSModelSpec) -> GenieTTSResourcePaths:
    resources = _validate_genie_tts_resources(settings, spec)

    os.environ["GENIE_DATA_DIR"] = str(resources.genie_data_dir)
    os.environ["GENIE_SKIP_RESOURCE_CHECK"] = "1"
    os.environ["English_G2P_DIR"] = str(resources.english_g2p_dir)
    os.environ["Chinese_G2P_DIR"] = str(resources.chinese_g2p_dir)
    os.environ["HUBERT_MODEL_DIR"] = str(resources.hubert_model_dir)
    os.environ["SV_MODEL"] = str(resources.sv_model_path)
    os.environ["ROBERTA_MODEL_DIR"] = str(resources.roberta_model_dir)
    return resources


def _import_genie_tts_module(settings: XnneHangLabSettings) -> Any:
    submodule_src_dir = _resolve_genie_tts_submodule_src_dir(settings)
    if not submodule_src_dir.is_dir():
        raise FileNotFoundError(f"Genie-TTS submodule source directory does not exist: {submodule_src_dir}")

    submodule_src_str = str(submodule_src_dir)
    if submodule_src_str not in sys.path:
        sys.path.insert(0, submodule_src_str)

    importlib.invalidate_caches()
    return importlib.import_module("genie_tts")


def get_genie_tts_status() -> dict[str, Any]:
    settings = _get_genie_tts_settings()
    configured: GenieTTSModelSpec | None = None
    configured_error: str | None = None
    resource_error: str | None = None
    resource_paths = _resolve_genie_tts_resource_paths(settings)

    try:
        configured = _get_configured_model_spec(settings)
    except Exception as exc:
        configured_error = str(exc)
    else:
        try:
            _validate_genie_tts_resources(settings, configured)
        except Exception as exc:
            resource_error = str(exc)

    return {
        "loaded": _genie_tts_module is not None,
        "configured_character": configured.character_name if configured is not None else None,
        "loaded_character": _loaded_model_spec.character_name if _loaded_model_spec is not None else None,
        "loaded_model_matches_config": _loaded_model_spec is not None
        and configured is not None
        and _loaded_model_spec == configured,
        "configured_model_dir": str(configured.onnx_model_dir) if configured is not None else None,
        "loaded_model_dir": str(_loaded_model_spec.onnx_model_dir) if _loaded_model_spec is not None else None,
        "language": configured.language if configured is not None else None,
        "use_roberta": configured.use_roberta if configured is not None else None,
        "submodule_src_dir": str(_resolve_genie_tts_submodule_src_dir(settings)),
        "genie_data_dir": str(resource_paths.genie_data_dir),
        "english_g2p_dir": str(resource_paths.english_g2p_dir),
        "chinese_g2p_dir": str(resource_paths.chinese_g2p_dir),
        "hubert_onnx_path": str(resource_paths.hubert_onnx_path),
        "hubert_fp16_weights_path": str(resource_paths.hubert_fp16_weights_path),
        "sv_model_path": str(resource_paths.sv_model_path),
        "roberta_model_dir": str(resource_paths.roberta_model_dir),
        "roberta_model_path": str(resource_paths.roberta_model_path),
        "sample_rate": DEFAULT_SAMPLE_RATE,
        "configured_error": configured_error,
        "resource_error": resource_error,
    }


def load_genie_tts_model(*, force_reload: bool = False) -> dict[str, Any]:
    global _genie_tts_module, _loaded_model_spec

    settings = _get_genie_tts_settings()
    if not settings.package.genie_tts:
        raise RuntimeError("Genie-TTS is disabled in lab.toml")

    target_spec = _get_configured_model_spec(settings)
    _configure_genie_tts_environment(settings, target_spec)

    with _model_lock:
        if _genie_tts_module is not None and _loaded_model_spec == target_spec and not force_reload:
            return get_genie_tts_status()
        if _genie_tts_module is not None:
            _tts_logger.info(
                "releasing genie-tts engine before reload "
                f"(current_character={_loaded_model_spec.character_name if _loaded_model_spec is not None else '-'})"
            )
            _release_engine()

        try:
            genie_tts = _import_genie_tts_module(settings)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("failed to import genie_tts from packages/Genie-TTS/src") from exc

        _tts_logger.info(
            "genie-tts load start: "
            f"character={target_spec.character_name}, model_dir={target_spec.onnx_model_dir}, "
            f"language={target_spec.language}, use_roberta={target_spec.use_roberta}"
        )
        genie_tts.load_character(
            character_name=target_spec.character_name,
            onnx_model_dir=str(target_spec.onnx_model_dir),
            language=target_spec.language,
            use_roberta=target_spec.use_roberta,
        )

        _genie_tts_module = genie_tts
        _loaded_model_spec = target_spec
        _tts_logger.info(f"genie-tts load complete: character={target_spec.character_name}")

    return get_genie_tts_status()


def reload_genie_tts_model() -> dict[str, Any]:
    return load_genie_tts_model(force_reload=True)


async def warmup_genie_tts_model() -> dict[str, Any]:
    settings = _get_genie_tts_settings()
    configured = _get_configured_model_spec(settings)
    ref_audio, ref_text = _resolve_warmup_ref_audio_and_text(settings, configured.character_name)

    started = time.perf_counter()
    _tts_logger.info(
        f"genie-tts warmup start: character={configured.character_name}, ref_audio={ref_audio}, text_len={len(ref_text)}"
    )
    wav_bytes = await asyncio.wait_for(
        synthesize_once(
            text=ref_text,
            ref_audio=ref_audio,
            ref_text=ref_text,
        ),
        timeout=120.0,
    )
    _tts_logger.info(
        f"genie-tts warmup complete: character={configured.character_name}, "
        f"audio_bytes={len(wav_bytes)}, sample_rate={read_wav_sample_rate(wav_bytes)}, "
        f"elapsed={time.perf_counter() - started:.2f}s"
    )
    return get_genie_tts_status()


def get_genie_tts_model() -> Any:
    settings = _get_genie_tts_settings()
    if not settings.package.genie_tts:
        raise HTTPException(status_code=503, detail="Genie-TTS is disabled in lab.toml")

    configured = _get_configured_model_spec(settings)
    if _genie_tts_module is None or _loaded_model_spec is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Genie-TTS model '{configured.character_name}' is not initialized. "
                "It should be loaded during application startup."
            ),
        )

    if _loaded_model_spec != configured:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Configured Genie-TTS character '{configured.character_name}' does not match the loaded character. "
                f"Currently loaded character: '{_loaded_model_spec.character_name}'. "
                "Restart the service to apply the new profile/model selection."
            ),
        )

    return _genie_tts_module


def get_sample_rate() -> int:
    return DEFAULT_SAMPLE_RATE


def _pcm_chunks_to_wav_bytes(chunks: list[bytes], sample_rate: int) -> bytes:
    if not chunks:
        raise RuntimeError("genie-tts returned no audio chunks")

    arrays = [np.frombuffer(chunk, dtype=np.int16) for chunk in chunks if chunk]
    if not arrays:
        raise RuntimeError("genie-tts returned only empty audio chunks")

    merged = np.concatenate(arrays, axis=0)
    buf = io.BytesIO()
    sf_write = cast("Any", sf).write
    sf_write(buf, merged, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


async def synthesize_once(*, text: str, ref_audio: Path | None, ref_text: str | None) -> bytes:
    genie_tts = get_genie_tts_model()
    configured = _loaded_model_spec
    if configured is None:
        raise HTTPException(status_code=503, detail="Genie-TTS model is not loaded")

    if ref_audio is None:
        raise HTTPException(status_code=400, detail="ref_audio_path is required")
    if not ref_audio.exists():
        raise HTTPException(status_code=404, detail=f"ref_audio_path not found: {ref_audio}")

    prompt_text = (ref_text or "").strip()
    if not prompt_text:
        raise HTTPException(status_code=400, detail="ref_text is required for genie-tts")

    async with _hold_model_lock_async():
        genie_tts.set_reference_audio(
            character_name=configured.character_name,
            audio_path=str(ref_audio),
            audio_text=prompt_text,
            use_roberta=configured.use_roberta,
        )

        chunks = [chunk async for chunk in genie_tts.tts_async(character_name=configured.character_name, text=text)]

    return _pcm_chunks_to_wav_bytes(chunks, DEFAULT_SAMPLE_RATE)


def stop_genie_tts_synthesis() -> None:
    genie_tts = _genie_tts_module
    if genie_tts is None:
        return

    try:
        stop = getattr(genie_tts, "stop", None)
        if callable(stop):
            stop()
            _tts_logger.info("genie-tts stop requested for current synthesis")
    except Exception as exc:
        _tts_logger.warning(f"genie-tts stop request failed: {exc}")


def read_wav_sample_rate(wav_bytes: bytes) -> int:
    with sf.SoundFile(io.BytesIO(wav_bytes)) as sound_file:
        return int(sound_file.samplerate)

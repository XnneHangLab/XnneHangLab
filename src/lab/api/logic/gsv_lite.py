from __future__ import annotations

import gc
import io
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import soundfile as sf
from fastapi import HTTPException
from loguru import logger

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.profile.schema import Profile

DEFAULT_SAMPLE_RATE = 32000

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
    return data


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
        for candidate in emotion_list.values():
            if not isinstance(candidate, dict):
                continue
            ref_wav_path = candidate.get("ref_wav_path")
            prompt_text = candidate.get("prompt_text")
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
        "loaded_model_matches_config": _loaded_model_spec is not None and configured is not None and _loaded_model_spec == configured,
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
                "releasing gsv-lite engine before reload (current_character={})",
                _loaded_model_spec.character_name if _loaded_model_spec is not None else "-",
            )
            _release_engine()

        try:
            from gsv_tts import TTS
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("gsv-tts-lite is not installed") from exc

        _tts_logger.info(
            "gsv-lite load start: character={}, gpt={}, sovits={}, models_dir={}",
            target_spec.character_name,
            target_spec.gpt_path,
            target_spec.sovits_path,
            target_spec.models_dir,
        )

        engine = TTS(models_dir=str(target_spec.models_dir))
        engine.load_gpt_model(str(target_spec.gpt_path))
        engine.load_sovits_model(str(target_spec.sovits_path))

        warmup_ref_audio, warmup_ref_text = _resolve_warmup_reference(settings, target_spec)
        if warmup_ref_audio is not None and warmup_ref_text:
            try:
                engine.infer(
                    spk_audio_path=str(warmup_ref_audio),
                    prompt_audio_path=str(warmup_ref_audio),
                    prompt_audio_text=warmup_ref_text,
                    text="System warmup.",
                )
                _tts_logger.info("gsv-lite warmup finished: character={}", target_spec.character_name)
            except Exception:
                _tts_logger.warning("gsv-lite warmup failed; continue with loaded engine")

        _gsv_lite_engine = engine
        _loaded_model_spec = target_spec
        _tts_logger.info("gsv-lite load complete: character={}", target_spec.character_name)

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
            detail=f"GSV-Lite model '{configured.character_name}' is not loaded. Call /tts/gsv-lite/load first.",
        )

    if _loaded_model_spec != configured:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Configured GSV-Lite character '{configured.character_name}' is not loaded. "
                f"Currently loaded character: '{_loaded_model_spec.character_name}'. "
                "Call /tts/gsv-lite/load or /tts/gsv-lite/reload."
            ),
        )

    return _gsv_lite_engine


def get_sample_rate() -> int:
    return DEFAULT_SAMPLE_RATE


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

    clip: Any = await model.infer_async(
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

    buf = io.BytesIO()
    sf.write(buf, clip.audio_data, clip.samplerate, format="WAV", subtype="PCM_16")
    return buf.getvalue()

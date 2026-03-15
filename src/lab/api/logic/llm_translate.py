from __future__ import annotations

from pathlib import Path

from loguru import logger

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.translate import LLMTranslateEngine


def _get_llm_translate_settings() -> XnneHangLabSettings:
    return load_settings_file("lab.toml", XnneHangLabSettings)


def resolve_llm_translate_model_path(settings: XnneHangLabSettings | None = None) -> Path | None:
    configured_model_path = (settings or _get_llm_translate_settings()).agent.translate.llm.model_path.strip()
    if not configured_model_path:
        return None

    candidate = Path(configured_model_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


def is_llm_translate_engine_loaded() -> bool:
    return LLMTranslateEngine.is_loaded()


def load_llm_translate_engine(settings: XnneHangLabSettings | None = None) -> LLMTranslateEngine:
    resolved_settings = settings or _get_llm_translate_settings()
    model_path = resolve_llm_translate_model_path(resolved_settings)
    if model_path is None:
        raise RuntimeError("[agent.translate.llm].model_path is not set in lab.toml")
    if not model_path.exists():
        raise FileNotFoundError(f"LLM translate model not found: {model_path}")

    logger.info("[LLMTranslate] Loading engine from {}", model_path)
    return LLMTranslateEngine.get_instance(
        model_path=model_path,
        n_gpu_layers=resolved_settings.agent.translate.llm.n_gpu_layers,
    )


def get_llm_translate_engine() -> LLMTranslateEngine:
    return load_llm_translate_engine()


def preload_configured_llm_translate_engine() -> bool:
    settings = _get_llm_translate_settings()
    model_path = resolve_llm_translate_model_path(settings)
    if model_path is None:
        logger.warning("[LLMTranslate] preload skipped: [agent.translate.llm].model_path is not set")
        return False

    load_llm_translate_engine(settings)
    return True


def unload_llm_translate_engine() -> None:
    LLMTranslateEngine.unload_instance()

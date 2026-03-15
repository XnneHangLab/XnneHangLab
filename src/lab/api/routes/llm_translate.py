from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from lab.api.clients.llm_translate_client import LLMTranslateRequest
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.translate import LLMTranslateEngine

router = APIRouter(prefix="/translate")


def _resolve_model_path(model_path: str) -> Path:
    candidate = Path(model_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


@router.get("/llm/health")
async def health() -> JSONResponse:
    """Check whether the local translation engine is loaded."""
    if LLMTranslateEngine._instance is None:
        logger.warning("[LLMTranslate] /health -> 503: engine is not loaded")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "LLM translate engine is not loaded"},
        )

    logger.debug("[LLMTranslate] /health -> 200: ok")
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.post("/llm")
async def llm_translate(request: Request) -> dict[str, object]:
    """
    Translate text with the local LLM engine.
    The model is loaded lazily and does not require an API key.
    """
    try:
        llm_request = LLMTranslateRequest.model_validate(await request.json())
    except ValueError as exc:
        logger.warning("[LLMTranslate] Failed to parse request data: {}", exc)
        return {"code": 400, "message": f"Failed to parse request data: {exc}"}

    agent_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    model_path = agent_settings.agent.llm_translate_model_path
    n_gpu_layers = agent_settings.agent.llm_translate_n_gpu_layers

    if not model_path:
        logger.warning("[LLMTranslate] llm_translate_model_path is not set in lab.toml")
        return {"code": 500, "message": "llm_translate_model_path is not set in lab.toml"}

    resolved_model_path = _resolve_model_path(model_path)
    if not resolved_model_path.exists():
        logger.warning("[LLMTranslate] Model file does not exist: {}", resolved_model_path)
        return {"code": 500, "message": f"LLM translate model not found: {resolved_model_path}"}

    logger.info(
        "[LLMTranslate] Translation request: '{}'... {} -> {}",
        llm_request.text[:30],
        llm_request.source_language,
        llm_request.target_language,
    )

    try:
        engine = LLMTranslateEngine.get_instance(
            model_path=resolved_model_path,
            n_gpu_layers=n_gpu_layers,
        )
    except Exception as exc:
        logger.exception("[LLMTranslate] Failed to initialize engine: {}", exc)
        return {"code": 500, "message": f"Failed to initialize LLM translate engine: {exc}"}

    try:
        loop = asyncio.get_running_loop()
        target_text = await loop.run_in_executor(
            None,
            engine.translate,
            llm_request.text,
            llm_request.source_language,
            llm_request.target_language,
        )
    except Exception as exc:
        logger.exception("[LLMTranslate] Translation failed: {}", exc)
        return {"code": 500, "message": f"LLM translate failed: {exc}"}

    return {
        "code": 200,
        "message": "success",
        "source_text": llm_request.text,
        "target_text": target_text,
    }

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from lab.api.clients.llm_translate_client import LLMTranslateRequest
from lab.api.logic.llm_translate import get_llm_translate_engine, is_llm_translate_engine_loaded

router = APIRouter(prefix="/translate")


@router.get("/llm/health")
async def health() -> JSONResponse:
    """Check whether the local translation engine is loaded."""
    if not is_llm_translate_engine_loaded():
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
    The model is preloaded during lifespan when configured and does not require an API key.
    """
    try:
        llm_request = LLMTranslateRequest.model_validate(await request.json())
    except ValueError as exc:
        logger.warning("[LLMTranslate] Failed to parse request data: {}", exc)
        return {"code": 400, "message": f"Failed to parse request data: {exc}"}

    logger.info(
        "[LLMTranslate] Translation request: '{}'... -> {}",
        llm_request.text[:30],
        llm_request.target_language,
    )

    try:
        engine = get_llm_translate_engine()
    except Exception as exc:
        logger.exception("[LLMTranslate] Failed to initialize engine: {}", exc)
        return {"code": 500, "message": f"Failed to initialize LLM translate engine: {exc}"}

    try:
        loop = asyncio.get_running_loop()
        target_text = await loop.run_in_executor(
            None,
            engine.translate,
            llm_request.text,
            llm_request.target_language,
        )
    except Exception as exc:
        logger.exception("[LLMTranslate] Translation failed: {}", exc)
        return {"code": 500, "message": f"LLM translate failed: {exc}"}

    logger.info(
        "[LLMTranslate] Translation result: '{}'... -> '{}'...",
        llm_request.text[:30],
        target_text[:60],
    )

    return {
        "code": 200,
        "message": "success",
        "source_text": llm_request.text,
        "target_text": target_text,
    }

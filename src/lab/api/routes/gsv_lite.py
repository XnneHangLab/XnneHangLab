from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from loguru import logger
from pydantic import BaseModel, Field

from lab.config_manager import XnneHangLabSettings, load_settings_file

router = APIRouter(prefix="/tts/gsv-lite", tags=["gsv-lite"])
_tts_logger = logger.bind(group="tts")


def _get_gsv_lite_logic_module():
    return import_module("lab.api.logic.gsv_lite")


def _resolve_local_path(raw_path: str | None) -> Path | None:
    if raw_path is None or not raw_path.strip():
        return None

    path = Path(raw_path.strip())
    if path.is_absolute():
        return path

    settings = load_settings_file("lab.toml", XnneHangLabSettings)
    return (Path(settings.root.root_dir) / path).resolve()


class GSVLiteGeneratePayload(BaseModel):
    text: str
    ref_audio_path: str | None = None
    ref_text: str | None = None
    speaker_audio_path: str | None = None
    top_k: int = Field(default=15, ge=1)
    top_p: float = Field(default=1.0, gt=0.0)
    temperature: float = Field(default=1.0, gt=0.0)
    repetition_penalty: float = Field(default=1.35, gt=0.0)
    noise_scale: float = Field(default=0.5, ge=0.0)
    speed: float = Field(default=1.0, gt=0.0)


@router.get("/health")
async def health() -> dict[str, Any]:
    gsv_lite_logic = _get_gsv_lite_logic_module()
    return {
        "status": "ok",
        "service": "gsv-lite",
        **gsv_lite_logic.get_gsv_lite_status(),
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    gsv_lite_logic = _get_gsv_lite_logic_module()
    return gsv_lite_logic.get_gsv_lite_status()


@router.post("/load")
async def load_model() -> JSONResponse:
    try:
        gsv_lite_logic = _get_gsv_lite_logic_module()
        status_payload = gsv_lite_logic.load_gsv_lite_model()
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "GSV-Lite model loaded successfully",
                "status": status_payload,
            },
        )
    except Exception as exc:
        _tts_logger.exception("load gsv-lite model failed")
        return JSONResponse(status_code=500, content={"code": 500, "message": str(exc)})


@router.post("/reload")
async def reload_model() -> JSONResponse:
    try:
        gsv_lite_logic = _get_gsv_lite_logic_module()
        status_payload = gsv_lite_logic.reload_gsv_lite_model()
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "GSV-Lite model reloaded successfully",
                "status": status_payload,
            },
        )
    except Exception as exc:
        _tts_logger.exception("reload gsv-lite model failed")
        return JSONResponse(status_code=500, content={"code": 500, "message": str(exc)})


@router.post("/generate")
async def generate(payload: GSVLiteGeneratePayload) -> Response:
    try:
        text = payload.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")

        ref_audio = _resolve_local_path(payload.ref_audio_path)
        speaker_audio = _resolve_local_path(payload.speaker_audio_path)

        gsv_lite_logic = _get_gsv_lite_logic_module()
        wav_bytes = await gsv_lite_logic.synthesize_once(
            text=text,
            ref_audio=ref_audio,
            ref_text=payload.ref_text,
            speaker_audio=speaker_audio,
            top_k=payload.top_k,
            top_p=payload.top_p,
            temperature=payload.temperature,
            repetition_penalty=payload.repetition_penalty,
            noise_scale=payload.noise_scale,
            speed=payload.speed,
        )

        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "Cache-Control": "no-cache",
                "X-Sample-Rate": str(gsv_lite_logic.get_sample_rate()),
            },
        )

    except HTTPException:
        raise
    except Exception as exc:
        _tts_logger.exception("gsv-lite generate failed")
        return JSONResponse(status_code=500, content={"error": str(exc)})

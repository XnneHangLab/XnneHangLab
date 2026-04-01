from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from loguru import logger
from pydantic import BaseModel

from lab.config_manager import XnneHangLabSettings, load_settings_file

router = APIRouter(prefix="/tts/genie-tts", tags=["genie-tts"])
_tts_logger = logger.bind(group="tts")


def _get_genie_tts_logic_module():
    return import_module("lab.api.logic.genie_tts")


def _resolve_local_path(raw_path: str | None) -> Path | None:
    if raw_path is None or not raw_path.strip():
        return None

    path = Path(raw_path.strip())
    if path.is_absolute():
        return path

    settings = load_settings_file("lab.toml", XnneHangLabSettings)
    return (Path(settings.root.root_dir) / path).resolve()


class GenieTTSGeneratePayload(BaseModel):
    text: str
    ref_audio_path: str | None = None
    ref_text: str | None = None


@router.get("/health")
async def health() -> dict[str, Any]:
    genie_tts_logic = _get_genie_tts_logic_module()
    status_payload = genie_tts_logic.get_genie_tts_status()
    if not status_payload.get("loaded", False):
        raise HTTPException(status_code=503, detail="Genie-TTS is not initialized")
    return {
        "status": "ok",
        "service": "genie-tts",
        **status_payload,
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    genie_tts_logic = _get_genie_tts_logic_module()
    return genie_tts_logic.get_genie_tts_status()


@router.post("/generate")
async def generate(payload: GenieTTSGeneratePayload) -> Response:
    try:
        text = payload.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")

        ref_audio = _resolve_local_path(payload.ref_audio_path)

        genie_tts_logic = _get_genie_tts_logic_module()
        wav_bytes = await genie_tts_logic.synthesize_once(
            text=text,
            ref_audio=ref_audio,
            ref_text=payload.ref_text,
        )

        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "Cache-Control": "no-cache",
                "X-Sample-Rate": str(genie_tts_logic.read_wav_sample_rate(wav_bytes)),
            },
        )

    except HTTPException:
        raise
    except Exception as exc:
        _tts_logger.exception("genie-tts generate failed")
        return JSONResponse(status_code=500, content={"error": str(exc)})

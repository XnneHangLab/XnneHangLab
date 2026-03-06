from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from loguru import logger
from pydantic import BaseModel

from lab.api.logic.faster_qwen_tts import synthesize_once, synthesize_stream

router = APIRouter(prefix="/tts/qwen-tts", tags=["qwen-tts"])
_tts_logger = logger.bind(group="tts")


class OpenAISpeechRequest(BaseModel):
    model: str
    input: str
    voice: str = "default"
    response_format: str = "wav"
    stream: bool = False


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "faster-qwen-tts"}


@router.get("/v1/models")
async def list_models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": "tts-1",
                "object": "model",
                "owned_by": "xnnehanglab",
            }
        ],
    }


async def _parse_request_payload(request: Request) -> tuple[OpenAISpeechRequest, Path | None, str | None, bool]:
    content_type = (request.headers.get("content-type") or "").lower()

    if "multipart/form-data" in content_type:
        form = await request.form()
        payload = OpenAISpeechRequest(
            model=str(form.get("model", "tts-1")),
            input=str(form.get("input", "")),
            voice=str(form.get("voice", "default")),
            response_format=str(form.get("response_format", "wav")),
            stream=str(form.get("stream", "false")).lower() in {"1", "true", "yes", "on"},
        )
        ref_text = str(form.get("ref_text")) if form.get("ref_text") else None
        ref_audio_path = None
        is_temp_ref_audio = False
        ref_audio_obj = form.get("ref_audio")
        if isinstance(ref_audio_obj, UploadFile):
            suffix = Path(ref_audio_obj.filename or "ref.wav").suffix or ".wav"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(await ref_audio_obj.read())
                ref_audio_path = Path(temp_file.name)
            is_temp_ref_audio = True
        return payload, ref_audio_path, ref_text, is_temp_ref_audio

    data = await request.json()
    payload = OpenAISpeechRequest.model_validate(data)

    ref_text_raw = data.get("ref_text")
    ref_text = str(ref_text_raw) if isinstance(ref_text_raw, str) else None

    ref_audio_raw = data.get("ref_audio")
    ref_audio_path = Path(ref_audio_raw) if isinstance(ref_audio_raw, str) and ref_audio_raw else None
    if ref_audio_path is not None and not ref_audio_path.exists():
        raise HTTPException(status_code=400, detail=f"ref_audio file not found: {ref_audio_path}")

    return payload, ref_audio_path, ref_text, False


@router.post("/v1/audio/speech")
async def create_speech(request: Request) -> Response:
    temp_ref_path: Path | None = None
    try:
        payload, ref_audio_path, ref_text, is_temp_ref_audio = await _parse_request_payload(request)
        temp_ref_path = ref_audio_path if is_temp_ref_audio and ref_audio_path and ref_audio_path.is_file() else None

        if payload.response_format.lower() != "wav":
            raise HTTPException(status_code=400, detail="Only wav response_format is supported")

        if payload.model != "tts-1":
            _tts_logger.warning(f"unsupported model requested: {payload.model}, fallback to tts-1")

        _tts_logger.info(f"qwen-tts request received: stream={payload.stream}, text_len={len(payload.input)}")

        if payload.stream:
            return StreamingResponse(
                synthesize_stream(text=payload.input, ref_audio=ref_audio_path, ref_text=ref_text),
                media_type="audio/wav",
                headers={"x-openai-model": "tts-1"},
            )

        wav_bytes = synthesize_once(text=payload.input, ref_audio=ref_audio_path, ref_text=ref_text)
        return Response(content=wav_bytes, media_type="audio/wav", headers={"x-openai-model": "tts-1"})
    except HTTPException:
        raise
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc
    except Exception as exc:
        _tts_logger.exception("create speech failed")
        return JSONResponse(status_code=500, content={"error": str(exc)})
    finally:
        if temp_ref_path is not None and temp_ref_path.exists():
            temp_ref_path.unlink(missing_ok=True)

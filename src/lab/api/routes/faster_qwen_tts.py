from __future__ import annotations

import asyncio
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from importlib import import_module
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from loguru import logger
from pydantic import BaseModel

router = APIRouter(prefix="/tts/qwen-tts", tags=["qwen-tts"])
_tts_logger = logger.bind(group="tts")
_qwen_tts_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qwen-tts")


def _get_qwen_tts_logic_module():
    return import_module("lab.api.logic.faster_qwen_tts")


class QwenTTSLoadPayload(BaseModel):
    model_name: str | None = None


@router.get("/health")
async def health() -> dict[str, Any]:
    qwen_tts_logic = _get_qwen_tts_logic_module()
    return {
        "status": "ok",
        "service": "faster-qwen-tts",
        **qwen_tts_logic.get_qwen_tts_status(),
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    qwen_tts_logic = _get_qwen_tts_logic_module()
    return qwen_tts_logic.get_qwen_tts_status()


@router.post("/load")
async def load_model(payload: QwenTTSLoadPayload | None = None) -> JSONResponse:
    try:
        qwen_tts_logic = _get_qwen_tts_logic_module()
        normalized_model = (
            qwen_tts_logic.normalize_qwen_tts_model_name(payload.model_name)
            if payload is not None and payload.model_name
            else None
        )
        loop = asyncio.get_running_loop()
        status_payload = await loop.run_in_executor(
            _qwen_tts_executor,
            partial(qwen_tts_logic.load_qwen_tts_model, normalized_model),
        )
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "Qwen-TTS model loaded successfully",
                "status": status_payload,
            },
        )
    except Exception as exc:
        _tts_logger.exception("load qwen-tts model failed")
        return JSONResponse(status_code=500, content={"code": 500, "message": str(exc)})


@router.post("/reload")
async def reload_model(payload: QwenTTSLoadPayload | None = None) -> JSONResponse:
    try:
        qwen_tts_logic = _get_qwen_tts_logic_module()
        normalized_model = (
            qwen_tts_logic.normalize_qwen_tts_model_name(payload.model_name)
            if payload is not None and payload.model_name
            else None
        )
        loop = asyncio.get_running_loop()
        status_payload = await loop.run_in_executor(
            _qwen_tts_executor,
            partial(qwen_tts_logic.reload_qwen_tts_model, normalized_model),
        )
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "Qwen-TTS model reloaded successfully",
                "status": status_payload,
            },
        )
    except Exception as exc:
        _tts_logger.exception("reload qwen-tts model failed")
        return JSONResponse(status_code=500, content={"code": 500, "message": str(exc)})


async def _save_upload_to_temp(upload: UploadFile | None) -> Path | None:
    if upload is None:
        return None

    suffix = Path(upload.filename or "ref.wav").suffix or ".wav"
    content = await upload.read()
    if not content:
        return None

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        return Path(temp_file.name)


@router.post("/generate")
async def generate_non_stream(
    text: str = Form(...),
    ref_text: str = Form(""),
    ref_audio: UploadFile | None = None,
) -> Response:
    temp_ref_path: Path | None = None

    try:
        text = text.strip()
        ref_text = ref_text.strip()

        if not text:
            raise HTTPException(status_code=400, detail="text is required")

        temp_ref_path = await _save_upload_to_temp(ref_audio)

        _tts_logger.info(
            f"qwen-tts non-stream request received: text_len={len(text)}, "
            f"has_ref_audio={temp_ref_path is not None}, has_ref_text={bool(ref_text)}"
        )

        qwen_tts_logic = _get_qwen_tts_logic_module()
        loop = asyncio.get_running_loop()
        wav_bytes = await loop.run_in_executor(
            _qwen_tts_executor,
            partial(
                qwen_tts_logic.synthesize_once,
                text=text,
                ref_audio=temp_ref_path,
                ref_text=ref_text or None,
            ),
        )

        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "Cache-Control": "no-cache",
            },
        )

    except HTTPException:
        raise
    except Exception as exc:
        _tts_logger.exception("non-stream generate failed")
        return JSONResponse(status_code=500, content={"error": str(exc)})
    finally:
        if temp_ref_path is not None and temp_ref_path.exists():
            temp_ref_path.unlink(missing_ok=True)


@router.post("/generate/stream")
async def generate_stream(
    text: str = Form(...),
    ref_text: str = Form(""),
    chunk_size: int = Form(8),
    ref_audio: UploadFile | None = None,
) -> StreamingResponse:
    temp_ref_path: Path | None = None

    try:
        text = text.strip()
        ref_text = ref_text.strip()

        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        if chunk_size < 1:
            raise HTTPException(status_code=400, detail="chunk_size must be >= 1")

        temp_ref_path = await _save_upload_to_temp(ref_audio)

        _tts_logger.info(
            f"qwen-tts stream request received: text_len={len(text)}, "
            f"has_ref_audio={temp_ref_path is not None}, has_ref_text={bool(ref_text)}, "
            f"chunk_size={chunk_size}"
        )

        async def _event_stream():
            try:
                qwen_tts_logic = _get_qwen_tts_logic_module()
                async for chunk in qwen_tts_logic.synthesize_stream(
                    text=text,
                    ref_audio=temp_ref_path,
                    ref_text=ref_text or None,
                    chunk_size=chunk_size,
                ):
                    yield chunk
            finally:
                if temp_ref_path is not None and temp_ref_path.exists():
                    temp_ref_path.unlink(missing_ok=True)

        return StreamingResponse(
            _event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        if temp_ref_path is not None and temp_ref_path.exists():
            temp_ref_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if temp_ref_path is not None and temp_ref_path.exists():
            temp_ref_path.unlink(missing_ok=True)
        _tts_logger.exception("stream generate failed")
        return StreamingResponse(
            iter([f'data: {{"type":"error","message":{exc!r}}}\n\n']),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

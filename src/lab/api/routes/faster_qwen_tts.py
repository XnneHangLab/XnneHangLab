from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from loguru import logger

from lab.api.logic.faster_qwen_tts import synthesize_once, synthesize_stream

router = APIRouter(prefix="/tts/qwen-tts", tags=["qwen-tts"])
_tts_logger = logger.bind(group="tts")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "faster-qwen-tts"}


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
            f"qwen-tts non-stream request received: text_len={len(text)}, has_ref_audio={temp_ref_path is not None}, has_ref_text={bool(ref_text)}"
        )

        wav_bytes = synthesize_once(
            text=text,
            ref_audio=temp_ref_path,
            ref_text=ref_text or None,
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
            f"qwen-tts stream request received: text_len={len(text)}, has_ref_audio={temp_ref_path is not None}, has_ref_text={bool(ref_text)}, chunk_size={chunk_size}"
        )

        async def _event_stream():
            try:
                async for chunk in synthesize_stream(
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

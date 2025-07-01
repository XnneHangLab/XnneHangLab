from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from vits.api.core_logic import process_text  # type: ignore
from vits.tools.ffmpeg_helper import audio_to_opus_bytes  # type: ignore

if TYPE_CHECKING:
    from vits.api._typing import TTSRequest

router = APIRouter()


@router.post("/tts/direct")
async def tts_direct(request: TTSRequest):
    """
    直接生成音频，不进行切分。
    """
    try:
        sample_rate, audio_data = process_text(request.text)  # type: ignore
        opus_bytes = audio_to_opus_bytes(sample_rate, audio_data)  # type: ignore
        return StreamingResponse(
            io.BytesIO(opus_bytes),
            media_type="audio/ogg",
            headers={"Content-Disposition": "attachment; filename=tts_output.opus"},
        )
    except Exception as e:
        logger.error(f"Error in direct TTS generation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating audio: {str(e)}") from e


async def generate_tts_direct(text: str, file_path: str):
    """
    直接生成音频，不进行切分，并保存为 Opus 文件。

    Args:
        text (str): 要转换为音频的文本内容。
        file_path (str): 保存生成音频文件的路径。

    Returns:
        str: 保存的音频文件路径。
    """
    try:
        path = Path(file_path)
        sample_rate, audio_data = process_text(text)  # type: ignore
        opus_bytes = audio_to_opus_bytes(sample_rate, audio_data)  # type: ignore
        # 确保文件目录存在
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            f.write(opus_bytes)
        logger.info(f"Audio file saved successfully at {file_path}")
        return str(path)
    except Exception as e:
        logger.error(f"Error in generating and saving TTS audio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating and saving audio: {str(e)}") from e

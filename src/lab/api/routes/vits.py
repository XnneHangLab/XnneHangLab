from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from vits.api._typing import TTSRequest
from vits.api.core_logic import process_text
from vits.state_manager import tts_state_manager
from vits.tools.ffmpeg_helper import audio_to_opus_bytes

router = APIRouter()


@router.post("/tts/direct")
async def tts_direct(request: TTSRequest):
    """
    直接生成音频，不进行切分。
    """
    try:
        sample_rate, audio_data = process_text(request.text)
        opus_bytes = audio_to_opus_bytes(sample_rate, audio_data)
        return StreamingResponse(
            io.BytesIO(opus_bytes),
            media_type="audio/ogg",
            headers={"Content-Disposition": "attachment; filename=tts_output.opus"},
        )
    except Exception as e:
        logger.error(f"Error in direct TTS generation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating audio: {str(e)}")


async def generate_tts_direct(text: str, file_path: Path):
    """
    直接生成音频，不进行切分，并保存为 Opus 文件。

    Args:
        text (str): 要转换为音频的文本内容。
        file_path (str): 保存生成音频文件的路径。

    Returns:
        str: 保存的音频文件路径。
    """
    try:
        sample_rate, audio_data = process_text(text)
        opus_bytes = audio_to_opus_bytes(sample_rate, audio_data)
        # 确保文件目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("wb") as f:
            f.write(opus_bytes)
        logger.info(f"Audio file saved successfully at {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Error in generating and saving TTS audio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating and saving audio: {str(e)}")

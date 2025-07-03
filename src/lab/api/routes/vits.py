from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from vits.api.core_logic import process_text  # type: ignore
from vits.tools.ffmpeg_helper import audio_to_opus_bytes  # type: ignore

from lab.api.clients.bert_vits_client import BERTVITSRequest

router = APIRouter()


@router.post("/tts/bert_vits")
async def bert_vits_direct(request: Request):
    """
    直接调用 vits 生成音频，不进行切分。
    """
    try:
        request = await request.json()
        _request = BERTVITSRequest.model_validate(request)
        sample_rate, audio_data = process_text(_request.text)  # type: ignore
        if _request.audio_type == "opus":
            audio_type = "opus"
            opus_bytes = audio_to_opus_bytes(sample_rate, audio_data)  # type: ignore
        else:
            raise ValueError(f"Unsupported audio type: {_request.audio_type}")
        return {
            "audio_byte": base64.b64encode(opus_bytes).decode("utf-8"),
            "audio_rate": sample_rate,
            "audio_type": audio_type,
        }
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

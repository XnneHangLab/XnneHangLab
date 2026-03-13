from __future__ import annotations

from typing import Any

from fastapi import APIRouter, UploadFile

from lab.api.logic.whisper import whisper_asr_audio
from lab.api.routes.asr_shared import file_default, save_upload_to_temp

router = APIRouter(prefix="/asr", tags=["asr", "whisper"])


@router.post("/whisper", response_model=dict)
async def whisper_with_punc(file: UploadFile = file_default) -> dict[str, Any]:
    """使用 Whisper 对上传音频执行识别。

    Args:
        file: 待识别的音频文件。

    Returns:
        dict[str, Any]: Whisper 识别结果以及统一的成功或失败消息。
    """
    temp_audio_path = save_upload_to_temp(file)
    try:
        result = whisper_asr_audio(input_path=temp_audio_path)
    except Exception as exc:
        temp_audio_path.unlink(missing_ok=True)
        return {"code": "500", "message": f"ASR processing failed: {exc}"}

    result["code"] = "200"
    result["message"] = "ASR processed successfully"
    temp_audio_path.unlink(missing_ok=True)
    return result

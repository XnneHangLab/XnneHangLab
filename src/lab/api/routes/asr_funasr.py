from __future__ import annotations

from typing import Any

from fastapi import APIRouter, UploadFile

from lab.api.logic.funasr import funasr_asr_audio, funasr_vad_audio
from lab.api.routes.asr_shared import file_default, save_upload_to_temp

router = APIRouter(prefix="/asr/funasr", tags=["asr", "funasr"])


@router.post("/with_punc", response_model=dict)
async def funasr_with_punc(file: UploadFile = file_default) -> dict[str, Any]:
    """使用 FunASR 对上传音频执行带标点识别。

    Args:
        file: 待识别的音频文件。

    Returns:
        dict[str, Any]: ASR 结果以及统一的成功或失败消息。
    """
    temp_audio_path = save_upload_to_temp(file)
    try:
        result = funasr_asr_audio(input_path=temp_audio_path, need_punc=True)
    except Exception as exc:
        temp_audio_path.unlink(missing_ok=True)
        return {"code": "500", "message": f"ASR processing failed: {exc}"}

    result["code"] = "200"
    result["message"] = "ASR processed successfully"
    temp_audio_path.unlink(missing_ok=True)
    return result


@router.post("/no_punc", response_model=dict)
async def funasr_no_punc(file: UploadFile = file_default) -> dict[str, Any]:
    """使用 FunASR 对上传音频执行不带标点识别。

    Args:
        file: 待识别的音频文件。

    Returns:
        dict[str, Any]: ASR 结果以及统一的成功或失败消息。
    """
    temp_audio_path = save_upload_to_temp(file)
    try:
        result = funasr_asr_audio(input_path=temp_audio_path, need_punc=False)
    except Exception as exc:
        temp_audio_path.unlink(missing_ok=True)
        return {"code": "500", "message": f"ASR processing failed: {exc}"}

    result["code"] = "200"
    result["message"] = "ASR processed successfully"
    temp_audio_path.unlink(missing_ok=True)
    return result


@router.post("/vad", response_model=dict)
async def funasr_vad_audio_activity(file: UploadFile = file_default) -> dict[str, Any]:
    """使用 FunASR 对上传音频执行 VAD 检测。

    Args:
        file: 待检测的音频文件。

    Returns:
        dict[str, Any]: VAD 结果以及统一的成功或失败消息。
    """
    temp_audio_path = save_upload_to_temp(file)
    try:
        result = funasr_vad_audio(input_path=temp_audio_path)
    except Exception as exc:
        temp_audio_path.unlink(missing_ok=True)
        return {"code": "500", "message": f"VAD processing failed: {exc}"}

    result["code"] = "200"
    result["message"] = "VAD processed successfully"
    temp_audio_path.unlink(missing_ok=True)
    return result

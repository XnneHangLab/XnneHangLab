from __future__ import annotations

from typing import Any

from fastapi import APIRouter, UploadFile

from lab.api.logic.funasr import funasr_asr_audio, funasr_vad_audio
from lab.api.routes.asr_shared import file_default, save_upload_to_temp
from lab.config_manager import XnneHangLabSettings, load_settings_file

router = APIRouter(prefix="/asr/funasr", tags=["asr", "funasr"])


@router.post("/transcribe", response_model=dict)
async def funasr_transcribe(file: UploadFile = file_default) -> dict[str, Any]:
    """使用 sherpa-onnx 处理上传音频。

    Args:
        file: 待识别音频文件。

    Returns:
        dict[str, Any]: 统一的 ASR 结果与状态字段。

    Raises:
        None.
    """
    temp_audio_path = save_upload_to_temp(file)
    try:
        lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
        if not lab_settings.package.asr:
            raise RuntimeError("Sherpa-ONNX is disabled in lab.toml")
        result = funasr_asr_audio(input_path=temp_audio_path)
    except Exception as exc:
        temp_audio_path.unlink(missing_ok=True)
        return {"code": "500", "message": f"ASR processing failed: {exc}"}

    result["code"] = "200"
    result["message"] = "ASR processed successfully"
    temp_audio_path.unlink(missing_ok=True)
    return result


@router.post("/vad", response_model=dict)
async def funasr_vad_audio_activity(file: UploadFile = file_default) -> dict[str, Any]:
    """使用 sherpa-onnx 执行 VAD 检测。

    Args:
        file: 待检测音频文件。

    Returns:
        dict[str, Any]: VAD 结果与状态字段。

    Raises:
        None.
    """
    temp_audio_path = save_upload_to_temp(file)
    try:
        lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
        if not lab_settings.package.asr:
            raise RuntimeError("Sherpa-ONNX is disabled in lab.toml")
        result = funasr_vad_audio(input_path=temp_audio_path)
    except Exception as exc:
        temp_audio_path.unlink(missing_ok=True)
        return {"code": "500", "message": f"VAD processing failed: {exc}"}

    result["code"] = "200"
    result["message"] = "VAD processed successfully"
    temp_audio_path.unlink(missing_ok=True)
    return result

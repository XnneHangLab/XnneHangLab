from __future__ import annotations

from typing import Any

from fastapi import APIRouter, UploadFile

from lab.api.logic.qwen_asr import normalize_qwen_model_name, qwen_asr_transcribe
from lab.api.routes.asr_shared import file_default, save_upload_to_temp
from lab.config_manager import XnneHangLabSettings, load_settings_file

router = APIRouter(prefix="/asr/qwen-asr", tags=["asr", "qwen-asr"])


async def _transcribe_qwen_model(file: UploadFile, model_name: str) -> dict[str, Any]:
    """使用指定的 Qwen3-ASR 模型处理上传音频。

    Args:
        file: 上传的音频文件。
        model_name: 路由传入的模型名称。

    Returns:
        dict[str, Any]: 统一的 ASR 结果。

    Raises:
        None.
    """
    temp_audio_path = save_upload_to_temp(file)
    try:
        lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
        if not lab_settings.package.qwen_asr:
            raise RuntimeError("Qwen3-ASR is disabled in lab.toml")
        result = qwen_asr_transcribe(
            input_path=temp_audio_path,
            model_name=normalize_qwen_model_name(model_name),
        )
    except Exception as exc:
        temp_audio_path.unlink(missing_ok=True)
        return {"code": "500", "message": f"Qwen3-ASR processing failed: {exc}"}

    result["code"] = "200"
    result["message"] = "Qwen3-ASR processed successfully"
    temp_audio_path.unlink(missing_ok=True)
    return result


@router.post("/0.6B/transcribe", response_model=dict)
async def qwen_asr_0_6b_transcribe(file: UploadFile = file_default) -> dict[str, Any]:
    """使用 Qwen3-ASR 0.6B 执行识别。

    Args:
        file: 上传的音频文件。

    Returns:
        dict[str, Any]: 统一的 ASR 结果。

    Raises:
        None.
    """
    return await _transcribe_qwen_model(file=file, model_name="0.6B")


@router.post("/1.7B/transcribe", response_model=dict)
async def qwen_asr_1_7b_transcribe(file: UploadFile = file_default) -> dict[str, Any]:
    """使用 Qwen3-ASR 1.7B 执行识别。

    Args:
        file: 上传的音频文件。

    Returns:
        dict[str, Any]: 统一的 ASR 结果。

    Raises:
        None.
    """
    return await _transcribe_qwen_model(file=file, model_name="1.7B")

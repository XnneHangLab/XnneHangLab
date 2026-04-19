from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

from fastapi import APIRouter, UploadFile

from lab.api.logic.sherpa_asr import sherpa_asr_audio, sherpa_vad_audio
from lab.api.routes.asr_shared import file_default, save_upload_to_temp
from lab.config_manager import XnneHangLabSettings, load_settings_file

router = APIRouter(prefix="/asr/sherpa", tags=["asr", "sherpa"])
_sherpa_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sherpa-asr")


@router.post("/transcribe", response_model=dict)
async def sherpa_transcribe(file: UploadFile = file_default) -> dict[str, Any]:
    """使用 Sherpa-ONNX Paraformer 处理上传音频。

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
        if lab_settings.asr.asr_model_provider != "sherpa":
            raise RuntimeError("Sherpa-ONNX is disabled in lab.toml")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _sherpa_executor,
            partial(sherpa_asr_audio, input_path=temp_audio_path),
        )
    except Exception as exc:
        temp_audio_path.unlink(missing_ok=True)
        return {"code": "500", "message": f"ASR processing failed: {exc}"}

    result["code"] = "200"
    result["message"] = "ASR processed successfully"
    temp_audio_path.unlink(missing_ok=True)
    return result


@router.post("/vad", response_model=dict)
async def sherpa_vad_audio_activity(file: UploadFile = file_default) -> dict[str, Any]:
    """使用 Sherpa-ONNX 执行 VAD 检测。

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
        if lab_settings.asr.asr_model_provider != "sherpa":
            raise RuntimeError("Sherpa-ONNX is disabled in lab.toml")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _sherpa_executor,
            partial(sherpa_vad_audio, input_path=temp_audio_path),
        )
    except Exception as exc:
        temp_audio_path.unlink(missing_ok=True)
        return {"code": "500", "message": f"VAD processing failed: {exc}"}

    result["code"] = "200"
    result["message"] = "VAD processed successfully"
    temp_audio_path.unlink(missing_ok=True)
    return result

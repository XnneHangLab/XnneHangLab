from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel

from lab.api.core_logic import rec_audio, reload_model, vad_audio  # 导入 load_model 用于预加载
from lab.config_manager import FunASRSettings, load_settings_file
from lab.utils.Timedhelper import get_time_tag_with_millis

# 加载配置文件
settings: FunASRSettings = load_settings_file("funasr.toml", FunASRSettings)

router = APIRouter(prefix="/audio")


# 确保输出目录和缓存目录存在
Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)


class ProcessConfig(BaseModel):
    only_text: bool = False
    cut: bool = False
    combine: bool = False
    debug: bool = False


file_default = File(...)


@router.post("/reload", response_model=dict)
async def reload():
    """
    Reload the FunASR model.
    Returns a message indicating the model has been reloaded.
    """
    try:
        reload_model()
    except Exception as e:
        return {"code": 500, "message": f"Failed to reload FunASR model: {str(e)}"}

    return {"code": 200, "message": "FunASR model has been reloaded successfully!"}


@router.post("/asr", response_model=dict)
async def recognize_audio(
    file: UploadFile = file_default,
    only_text: bool = Query(False, description="Whether to use only text mode (faster, no punctuation)"),
) -> dict[str, Any]:
    """
    Convert uploaded audio file to SRT format.
    Returns processing information and the path to the generated SRT file.
    """
    # 定义临时文件路径，如果文件名不存在则使用默认值
    temp_audio_path = Path(settings.cache_dir) / (
        file.filename if file.filename else f"temp_audio_{get_time_tag_with_millis()}.wav"
    )
    # 确保缓存目录存在
    temp_audio_path.parent.mkdir(parents=True, exist_ok=True)
    # 以二进制写入模式打开文件，并将上传的文件内容写入
    with temp_audio_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # TODO 检查文件完整性
    # 处理音频文件
    try:
        result = rec_audio(input_path=temp_audio_path)
    except Exception as e:
        return {"code": "500", "message": f"ASR processing failed: {str(e)}"}
    result["code"] = "200"
    result["message"] = "ASR processed successfully"
    # 清理临时文件
    temp_audio_path.unlink(missing_ok=True)
    return result


# (base) pi@raspberrypi:~/Desktop/XnneHangLab $ time curl -X POST "http://127.0.0.1:8000/rec-audio"       -F "file=@/home/xnne/code/XnneHangLab/examples/example3.opus"
# {"processing_time":0.5680921077728271,"text":"那年，长街春意正浓，策马同游。"}
# real	0m0.619s
# user	0m0.011s
# sys	0m0.015s


@router.post("/vad", response_model=dict)
async def vad_audio_activity(
    file: UploadFile = file_default,
):
    """
    Perform Voice Activity Detection (VAD) on the uploaded audio file.
    Returns processing information and the path to the generated VAD results.
    """
    # 定义临时文件路径，如果文件名不存在则使用默认值
    temp_audio_path = Path(settings.cache_dir) / (
        file.filename if file.filename else f"temp_audio_{get_time_tag_with_millis()}.wav"
    )
    # 确保缓存目录存在
    temp_audio_path.parent.mkdir(parents=True, exist_ok=True)
    # 以二进制写入模式打开文件，并将上传的文件内容写入
    with temp_audio_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # TODO 检查文件完整性
    # 处理音频文件
    try:
        result = vad_audio(input_path=temp_audio_path)
    except Exception as e:
        return {"code": "500", "message": f"VAD processing failed: {str(e)}"}
    # 清理临时文件
    result["code"] = "200"
    result["message"] = "VAD processed successfully"
    temp_audio_path.unlink(missing_ok=True)
    return result

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import File, UploadFile

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.utils.Timedhelper import get_time_tag_with_millis

lab_settings: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)

Path(lab_settings.asr.output_dir).mkdir(parents=True, exist_ok=True)
Path(lab_settings.asr.cache_dir).mkdir(parents=True, exist_ok=True)

file_default = File(...)


def save_upload_to_temp(file: UploadFile) -> Path:
    """将上传音频保存到 ASR 缓存目录中的临时文件。

    Args:
        file: FastAPI 接收到的上传文件对象。

    Returns:
        Path: 已写入磁盘的临时音频文件路径。
    """
    temp_audio_path = Path(lab_settings.asr.cache_dir) / (
        file.filename or f"temp_audio_{get_time_tag_with_millis()}.wav"
    )
    temp_audio_path.parent.mkdir(parents=True, exist_ok=True)
    with temp_audio_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return temp_audio_path

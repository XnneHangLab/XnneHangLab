from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Query, UploadFile
from pydantic import BaseModel

from lab._dataclass import RunnerSettings
from lab.api.core_logic import load_model, rec_audio  # 导入 load_model 用于预加载
from lab.utils.config import load_settings_file
from lab.utils.console.logger import Logger

# 加载配置文件
settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)

# 确保输出目录和缓存目录存在
Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)


class ProcessConfig(BaseModel):
    only_text: bool = False
    cut: bool = False
    combine: bool = False
    debug: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时执行：预加载模型
    Logger.info("Preloading FunASR model at startup...")
    load_model(only_text=False)  # 预加载模型，确保模型在启动时初始化
    Logger.info("FunASR model preloaded successfully.")
    yield
    # 应用关闭时执行：可选，清理资源
    Logger.info("Shutting down FastAPI application.")


app = FastAPI(title="Audio to SRT API", description="API for converting audio to SRT subtitles", lifespan=lifespan)


file_default = File(...)


@app.post("/rec-audio", response_model=dict)
async def convert_audio_to_srt(
    file: UploadFile = file_default,
    only_text: bool = Query(False, description="Whether to use only text mode (faster, no punctuation)"),
):
    """
    Convert uploaded audio file to SRT format.
    Returns processing information and the path to the generated SRT file.
    """
    # 定义临时文件路径，如果文件名不存在则使用默认值
    temp_audio_path = Path(settings.cache_dir) / (file.filename if file.filename else "temp_audio.wav")
    # 确保缓存目录存在
    temp_audio_path.parent.mkdir(parents=True, exist_ok=True)
    # 以二进制写入模式打开文件，并将上传的文件内容写入
    with temp_audio_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # TODO 检查文件完整性
    # 处理音频文件
    result = rec_audio(input_path=temp_audio_path, only_text=only_text)
    # 清理临时文件
    temp_audio_path.unlink(missing_ok=True)
    return result


# (base) pi@raspberrypi:~/Desktop/XnneHangLab $ time curl -X POST "http://127.0.0.1:8000/rec-audio"       -F "file=@/home/xnne/code/XnneHangLab/examples/example3.opus"
# {"processing_time":0.5680921077728271,"text":"那年，长街春意正浓，策马同游。"}
# real	0m0.619s
# user	0m0.011s
# sys	0m0.015s

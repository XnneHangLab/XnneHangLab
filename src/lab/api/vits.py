from __future__ import annotations

import gc
import io
import logging
import os
import wave
from contextlib import asynccontextmanager
from typing import Tuple

import numpy as np
import torch
import vits.re_matching as re_matching
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from vits import utils
from vits.config import config
from vits.infer import get_net_g, infer, latest_version
from vits.tools.ffmpeg_helper import audio_to_opus_bytes

# 设置日志
logging.basicConfig(level=logging.INFO, format="| %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# 全局变量，用于存储模型和配置
net_g = None
hps = None
device = config.webui_config.device
if device == "mps":
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"


# 转换音频为 16 位 WAV 格式
def convert_to_16_bit_wav(audio_array, dtype=np.int16):
    if audio_array.max() > 1.0 or audio_array.min() < -1.0:
        audio_array = np.clip(audio_array, -1.0, 1.0)
    if dtype == np.int16:
        audio_array = (audio_array * 32767).astype(np.int16)
    return audio_array


# 释放内存
def free_up_memory():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# 生成音频的核心逻辑
def generate_audio(
    slices,
    sdp_ratio=0.5,
    noise_scale=0.6,
    noise_scale_w=0.9,
    length_scale=1.0,
    speaker="xishi",
    language="ZH",
    reference_audio=None,
    emotion="Happy",
    style_text=None,
    style_weight=0.7,
    skip_start=False,
    skip_end=False,
):
    audio_list = []
    free_up_memory()
    with torch.no_grad():
        for idx, piece in enumerate(slices):
            skip_start = idx != 0
            skip_end = idx != len(slices) - 1
            audio = infer(
                piece,
                reference_audio=reference_audio,
                emotion=emotion,
                sdp_ratio=sdp_ratio,
                noise_scale=noise_scale,
                noise_scale_w=noise_scale_w,
                length_scale=length_scale,
                sid=speaker,
                language=language,
                hps=hps,
                net_g=net_g,
                device=device,
                skip_start=skip_start,
                skip_end=skip_end,
                style_text=style_text,
                style_weight=style_weight,
            )
            audio16bit = convert_to_16_bit_wav(audio)
            audio_list.append(audio16bit)
    return audio_list


# 直接生成音频
def process_text(
    text: str,
    speaker="xishi",
    sdp_ratio=0.5,
    noise_scale=0.6,
    noise_scale_w=0.9,
    length_scale=1.0,
    language="ZH",
    reference_audio=None,
    emotion="Happy",
    style_text=None,
    style_weight=0.7,
):
    audio_list = generate_audio(
        text.split("|"),
        sdp_ratio,
        noise_scale,
        noise_scale_w,
        length_scale,
        speaker,
        language,
        reference_audio,
        emotion,
        style_text,
        style_weight,
    )
    audio_concat = np.concatenate(audio_list)
    return hps.data.sampling_rate, audio_concat


# 切分生成音频
def tts_split(
    text: str,
    speaker="xishi",
    sdp_ratio=0.5,
    noise_scale=0.6,
    noise_scale_w=0.9,
    length_scale=1.0,
    language="ZH",
    cut_by_sent=True,
    interval_between_para=1.0,
    interval_between_sent=0.2,
    reference_audio=None,
    emotion="Happy",
    style_text=None,
    style_weight=0.7,
):
    while text.find("\n\n") != -1:
        text = text.replace("\n\n", "\n")
    text = text.replace("|", "")
    para_list = re_matching.cut_para(text)
    para_list = [p for p in para_list if p != ""]
    audio_list = []
    for p in para_list:
        if not cut_by_sent:
            audio_list += process_text(
                p,
                speaker,
                sdp_ratio,
                noise_scale,
                noise_scale_w,
                length_scale,
                language,
                reference_audio,
                emotion,
                style_text,
                style_weight,
            )
            silence = np.zeros((int)(44100 * interval_between_para), dtype=np.int16)
            audio_list.append(silence)
        else:
            audio_list_sent = []
            sent_list = re_matching.cut_sent(p)
            sent_list = [s for s in sent_list if s != ""]
            for s in sent_list:
                audio_list_sent += process_text(
                    s,
                    speaker,
                    sdp_ratio,
                    noise_scale,
                    noise_scale_w,
                    length_scale,
                    language,
                    reference_audio,
                    emotion,
                    style_text,
                    style_weight,
                )
                silence = np.zeros((int)(44100 * interval_between_sent), dtype=np.int16)
                audio_list_sent.append(silence)
            if (interval_between_para - interval_between_sent) > 0:
                silence = np.zeros((int)(44100 * (interval_between_para - interval_between_sent)), dtype=np.int16)
                audio_list_sent.append(silence)
            audio16bit = convert_to_16_bit_wav(np.concatenate(audio_list_sent))
            audio_list.append(audio16bit)
    audio_concat = np.concatenate(audio_list)
    return hps.data.sampling_rate, audio_concat


# 将音频数据转换为 WAV 格式的字节流
def audio_to_wav_bytes(sample_rate: int, audio_data: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)  # 单声道
        wav_file.setsampwidth(2)  # 16 位
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())
    return buffer.getvalue()


# 定义输入模型
class TTSRequest(BaseModel):
    text: str


# 应用生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    global net_g, hps
    logger.info("Loading TTS model...")
    hps = utils.get_hparams_from_file(config.webui_config.config_path)
    version = hps.version if hasattr(hps, "version") else latest_version
    net_g = get_net_g(model_path=config.webui_config.model, version=version, device=device, hps=hps)
    logger.info("TTS model loaded successfully.")
    yield
    logger.info("Unloading TTS model...")
    if net_g is not None:
        del net_g
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()
    logger.info("TTS model unloaded.")


# 创建 FastAPI 应用
app = FastAPI(lifespan=lifespan)


@app.post("/tts/direct")
async def generate_tts_direct(request: TTSRequest):
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


@app.post("/tts/split")
async def generate_tts_split(request: TTSRequest):
    """
    按段落和句子切分生成音频。
    """
    try:
        sample_rate, audio_data = tts_split(request.text)
        opus_bytes = audio_to_opus_bytes(sample_rate, audio_data)
        return StreamingResponse(
            io.BytesIO(opus_bytes),
            media_type="audio/ogg",
            headers={"Content-Disposition": "attachment; filename=tts_output.opus"},
        )
    except Exception as e:
        logger.error(f"Error in split TTS generation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating audio: {str(e)}")

# (全局的)对外部开放的 api logic 都会在这里, 而不对外开放的比如 database logic 在对应的模块里

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from funasr import AutoModel
from loguru import logger  # 保持 loguru 在代码顶部导入

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.funasr.method import generate_asr_results, generate_vad_results

if TYPE_CHECKING:
    from pathlib import Path

    from lab._typing import ASRResponse, VadResponse
    from lab.api._typing import ModelInstance


class FunASRModel:  # 对于 api 需要快速响应, 不能 lazy-import ,所以独立出来一个版本.
    def __init__(self):
        self.settings = load_settings_file("lab.toml", XnneHangLabSettings)
        self.base_model: str = str(self.settings.asr.funasr.base_model)
        self.vad_model: str = str(self.settings.asr.funasr.vad_model)
        self.punc_model: str = str(self.settings.asr.funasr.punc_model)
        self.sense_voice_model: str = str(self.settings.asr.funasr.sense_voice_model)
        self.device: str = self.settings.asr.device
        self._model: ModelInstance = {"asr": None, "vad": None, "asr_no_punc": None}  # 存储模型实例

    def init_model(self):
        """初始化模型"""
        if self._model["asr"] is None:
            self._model["asr"] = self.asr_full_version()
        if self._model["vad"] is None:
            self._model["vad"] = self.only_vad()
        if self._model["asr_no_punc"] is None:
            self._model["asr_no_punc"] = self.asr_no_punc_version()
        return self._model

    def reload_model(self):
        self._model = {"asr": None, "vad": None, "asr_no_punc": None}  # 重置模型实例
        self.init_model()

    def asr_full_version(self):
        if self._model["asr"] is None:  # 第一次加载时初始化模型
            logger.info("Loading FunASR model...")
            self._model["asr"] = AutoModel(
                model=self.base_model,
                vad_model=self.vad_model,
                punc_model=self.punc_model,
                device=self.device,
                disable_update=True,
            )
            logger.info("ASR 模型加载成功!")
        return self._model["asr"]

    def asr_no_punc_version(self):
        if self._model["asr_no_punc"] is None:  # 第一次加载时初始化模型
            logger.info("Loading ASR no punc model...")
            self._model["asr_no_punc"] = AutoModel(
                model=self.base_model,
                device=self.device,
                disable_update=True,
            )
            logger.info("ASR no punc 模型加载成功!")
        return self._model["asr_no_punc"]

    def only_vad(self):
        """仅加载 VAD 模型"""
        if self._model["vad"] is None:  # 第一次加载时初始化模型
            logger.info("Loading VAD model...")
            self._model["vad"] = AutoModel(
                model=self.vad_model,
                device=self.device,
                disable_update=True,
            )
            logger.info("VAD 模型加载成功!")
            return self._model["vad"]


# 全局模型实例（单例模式）
_model_instance = None


def load_model(lab_settings: XnneHangLabSettings) -> Any:
    """加载或获取 FunASR 模型（单例模式）"""
    global _model_instance
    if _model_instance is None:
        _model_instance = FunASRModel()
    return _model_instance.init_model()


def reload_model() -> Any:
    """重新加载 FunASR 模型"""
    global _model_instance
    if _model_instance is not None:
        _model_instance.reload_model()
    return _model_instance


def rec_audio(
    input_path: Path,
) -> dict[str, Any]:
    """处理音频文件并生成 SRT,返回结果信息"""
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    model_instances: ModelInstance = load_model(lab_settings)
    if model_instances["asr"] is not None:
        model: AutoModel = model_instances["asr"]
    else:
        return {"error": "ASR model is not loaded."}
    start = time.time()
    # 生成 ASR 结果
    response: ASRResponse = generate_asr_results(model=model, input_path=input_path)
    end = time.time()
    processing_time = end - start
    result = {
        "key": response["key"],
        "processing_time": processing_time,
        "text": response["text"],
        "timestamp": response["timestamp"],
    }
    return result


def rec_audio_no_punc(
    input_path: Path,
) -> dict[str, Any]:
    """处理音频文件并生成 SRT,返回结果信息"""
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    model_instances: ModelInstance = load_model(lab_settings)
    if model_instances["asr_no_punc"] is not None:
        model: AutoModel = model_instances["asr_no_punc"]
    else:
        return {"error": "ASR model is not loaded."}
    start = time.time()
    # 生成 ASR 结果
    response: ASRResponse = generate_asr_results(model=model, input_path=input_path)
    end = time.time()
    processing_time = end - start
    result = {
        "key": response["key"],
        "processing_time": processing_time,
        "text": response["text"],
        "timestamp": response["timestamp"],
    }
    return result


def vad_audio(
    input_path: Path,
):
    """处理音频文件并生成 SRT,返回结果信息"""
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    model_instances: ModelInstance = load_model(lab_settings)
    if model_instances["vad"] is not None:
        model: AutoModel = model_instances["vad"]
    else:
        return {"error": "VAD model is not loaded."}
    start = time.time()
    # 生成 ASR 结果
    response: VadResponse = generate_vad_results(model=model, input_path=input_path)
    end = time.time()
    processing_time = end - start
    result = {
        "key": response["key"],
        "processing_time": processing_time,
        "timestamp": response["timestamp"],
        "audio_length": response["audio_length"],
    }
    return result


# def bert_vits_gen(
#         text: str,
#         file_name: Path):
#     from vits.api_server import process_text
#     audio_rate, audio_bytes = process_text(text)
#     # 保存音频文件


async def async_rec_audio(
    input_path: Path,
    # only_text: bool = False, # only_text 暂不考虑
) -> dict[str, Any]:
    """处理音频文件并生成 SRT,返回结果信息"""
    # 假设 load_model 是同步函数，使用 asyncio.to_thread 在单独线程中运行
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    model_instances: ModelInstance = await asyncio.to_thread(load_model, lab_settings)
    if model_instances["asr"] is not None:
        model = model_instances["asr"]
    else:
        return {"error": "ASR model is not loaded."}
    start = time.time()
    # 假设 generate_asr_results 是同步函数，使用 asyncio.to_thread 在单独线程中运行
    response: ASRResponse = await asyncio.to_thread(generate_asr_results, model=model, input_path=input_path)
    end = time.time()
    processing_time = end - start
    result = {
        "key": response["key"],
        "processing_time": processing_time,
        "text": response["text"],
        "time_stamp": response["timestamp"],
    }
    return result

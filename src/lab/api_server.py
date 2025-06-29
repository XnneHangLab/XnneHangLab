from __future__ import annotations

import gc
from contextlib import asynccontextmanager
from pathlib import Path

# from app.core.db import client, init_mongo
# from app.core.exception_handler import biz_exception_handler
# from app.exceptions.base import BizException
from typing import TYPE_CHECKING

import torch
from fastapi import FastAPI
from loguru import logger
from vits import utils
from vits.infer import get_net_g, infer, infer_multilang, latest_version

from lab.api.core_logic import load_model
from lab.api.main import api_router
from lab.config_manager import FunASRSettings, load_settings_file
from lab.utils import utils
from lab.utils.console.logger import Logger

if TYPE_CHECKING:
    from fastapi.routing import APIRoute
import os

from vits.config import config

# 全局变量，用于存储模型和配置
net_g = None
hps = None
device = config.webui_config.device
if device == "mps":
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

# 加载配置文件
settings: FunASRSettings = load_settings_file("funasr.toml", FunASRSettings)

# 确保输出目录和缓存目录存在
Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时执行：预加载模型
    Logger.info("预加载 FunASR 模型...")
    load_model()  # 预加载模型，确保模型在启动时初始化
    global net_g, hps
    logger.info("Loading TTS model...")
    hps = utils.get_hparams_from_file(config.webui_config.config_path)
    version = hps.version if hasattr(hps, "version") else latest_version
    net_g = get_net_g(model_path=config.webui_config.model, version=version, device=device, hps=hps)
    logger.info("TTS model loaded successfully.")
    # await init_mongo(client, settings.MONGO_DB)
    yield  # 在 asynccontextmanager 装饰的函数中，yield 是一个分界点，它将函数的执行分为两个阶段： 启动和关闭
    # TODO 可能需要清理一下 cache
    logger.info("Unloading TTS model...")
    if net_g is not None:
        del net_g
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()
    logger.info("TTS model unloaded.")
    Logger.info("关闭程序.")


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


app = FastAPI(
    title="XnneHangLab BackEnd API",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")

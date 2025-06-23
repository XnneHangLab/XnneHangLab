from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

# from app.core.db import client, init_mongo
# from app.core.exception_handler import biz_exception_handler
# from app.exceptions.base import BizException
from typing import TYPE_CHECKING

from fastapi import FastAPI

from lab._dataclass import RunnerSettings
from lab.api.core_logic import load_model
from lab.api.main import api_router
from lab.utils.config import load_settings_file
from lab.utils.console.logger import Logger

if TYPE_CHECKING:
    from fastapi.routing import APIRoute

# 加载配置文件
settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)

# 确保输出目录和缓存目录存在
Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时执行：预加载模型
    Logger.info("预加载 FunASR 模型...")
    load_model()  # 预加载模型，确保模型在启动时初始化
    # await init_mongo(client, settings.MONGO_DB)
    yield  # 在 asynccontextmanager 装饰的函数中，yield 是一个分界点，它将函数的执行分为两个阶段： 启动和关闭
    # TODO 可能需要清理一下 cache
    Logger.info("关闭程序.")


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


app = FastAPI(
    title="XnneHangLab BackEnd API",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")

from __future__ import annotations

import gc
import os
from contextlib import asynccontextmanager
from pathlib import Path

import torch
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from vits import utils
from vits.config import config
from vits.infer import get_net_g, latest_version
from vits.state_manager import tts_state_manager

from lab._dataclass import RootAbsDir
from lab.api.core_logic import load_model
from lab.api.routes.vits import router as vits_router
from lab.config_manager.config import load_settings_file
from lab.config_manager.vtuber.utils import Config

from .routes import init_client_ws_route, init_webtool_routes
from .service_context import ServiceContext

RootSettings: RootAbsDir = load_settings_file("root.toml", RootAbsDir)
ROOT_DIR = Path(RootSettings.root_dir) / "static"

# 全局变量，用于存储模型和配置
device = config.webui_config.device
if device == "mps":
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

if not ROOT_DIR.exists():
    raise FileNotFoundError(f"Static root directory {ROOT_DIR} does not exist.")


class CustomStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if path.endswith(".js"):
            response.headers["Content-Type"] = "application/javascript"
        return response


class AvatarStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        allowed_extensions = (".jpg", ".jpeg", ".png", ".gif", ".svg")
        if not any(path.lower().endswith(ext) for ext in allowed_extensions):
            return Response("Forbidden file type", status_code=403)
        return await super().get_response(path, scope)


# 应用生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("预加载 FunASR 模型...")
    load_model()  # 预加载模型，确保模型在启动时初始化
    logger.info("Loading TTS model...")
    hps = utils.get_hparams_from_file(config.webui_config.config_path)
    version = hps.version if hasattr(hps, "version") else latest_version
    net_g = get_net_g(model_path=config.webui_config.model, version=version, device=device, hps=hps)
    # 设置单例状态
    tts_state_manager.set_state(net_g, hps)
    logger.info("TTS model loaded successfully.")
    yield
    logger.info("Unloading TTS model...")
    net_g = tts_state_manager.get_net_g()
    if net_g is not None:
        del net_g
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()
    # 重置单例状态
    tts_state_manager.set_state(None, None)
    logger.info("TTS model unloaded.")


class WebSocketServer:
    def __init__(self, config: Config):
        # def __init__(self):
        self.app = FastAPI(lifespan=lifespan)

        # Add CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Load configurations and initialize the default context cache
        default_context_cache = ServiceContext()
        default_context_cache.load_from_config(config)

        # Include routes
        self.app.include_router(
            init_client_ws_route(default_context_cache=default_context_cache),
        )
        self.app.include_router(
            init_webtool_routes(default_context_cache=default_context_cache),
        )
        self.app.include_router(vits_router)

        # Mount cache directory first (to ensure audio file access)
        # if not os.path.exists("cache"):
        # os.makedirs("cache")
        # self.app.mount(
        #     "/cache",
        #     StaticFiles(directory="cache"),
        #     name="cache",
        # )

        # Mount static files
        logger.info(f"Mounting static files from {ROOT_DIR}")
        self.app.mount(
            "/live2d-models",
            StaticFiles(directory=(ROOT_DIR / "live2d-models")),
            name="live2d-models",
        )
        self.app.mount(
            "/bg",
            StaticFiles(directory=str(ROOT_DIR / "backgrounds")),
            name="backgrounds",
        )
        self.app.mount(
            "/avatars",
            AvatarStaticFiles(directory=str(ROOT_DIR / "avatars")),
            name="avatars",
        )
        # Mount web tool directory separately from frontend
        self.app.mount(
            "/web-tool",
            CustomStaticFiles(directory=str(ROOT_DIR / "web_tool"), html=True),
            name="web_tool",
        )

        # Mount main frontend last (as catch-all)
        # self.app.mount(
        #     "/",
        #     CustomStaticFiles(directory="frontend", html=True),
        #     name="frontend",
        # )

    def run(self):
        pass

    # @staticmethod
    # def clean_cache():
    #     """Clean the cache directory by removing and recreating it."""
    #     cache_dir = "cache"
    #     if os.path.exists(cache_dir):
    #         shutil.rmtree(cache_dir)
    #         os.makedirs(cache_dir)

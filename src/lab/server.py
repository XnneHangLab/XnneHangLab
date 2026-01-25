from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from lab.api.routes.deeplx import router as deeplx_router
from lab.api.routes.vtuber import init_client_ws_route, router as vtuber_router
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.service_context import ServiceContext

if TYPE_CHECKING:
    from lab.config_manager.vtuber.utils import Config as vtuber_config

lab_settings: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)

ROOT_DIR = Path(lab_settings.root.root_dir) / "static"


if not ROOT_DIR.exists():
    raise FileNotFoundError(f"Static root directory {ROOT_DIR} does not exist.")


class CustomStaticFiles(StaticFiles):
    async def get_response(self, path, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if path.endswith(".js"):
            response.headers["Content-Type"] = "application/javascript"
        return response


class AvatarStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):  # type: ignore[override]
        allowed_extensions = (".jpg", ".jpeg", ".png", ".gif", ".svg")
        if not any(path.lower().endswith(ext) for ext in allowed_extensions):
            return Response("Forbidden file type", status_code=403)
        return await super().get_response(path, scope)


# 应用生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 之所以做这些 packages 的区分，是因为我们的 Base_URL 可以调用远程，不一定要运行在本地。
    if lab_settings.package.funasr:
        from lab.api.core_logic import load_model

        logger.info("预加载 FunASR 模型...")
        load_model()  # 预加载模型，确保模型在启动时初始化

    if lab_settings.package.gpt_sovits:
        # 应用启动时执行
        # 动态导入合成器模块, 此处可写成 from gsv.Synthesizers.xxx import TTS_Synthesizer, TTS_Task
        from importlib import import_module

        from gsv.gsv_state_manager import gsv_tts_state_manager

        logger.info("预加载 GPT-SoVITS 模型...")
        synthesizer_name = "gsv_fast"
        synthesizer_module = import_module(f"gsv.Synthesizers.{synthesizer_name}")
        TTS_Synthesizer = synthesizer_module.TTS_Synthesizer
        # TTS_Task = synthesizer_module.TTS_Task
        # 初始化合成器的类
        tts_synthesizer = TTS_Synthesizer(debug_mode=True)
        gsv_tts_state_manager.set_state(tts_synthesizer)
        # 生成一句话充当测试，减少第一次请求的等待时间
        gen = tts_synthesizer.generate(tts_synthesizer.params_parser({"text": "筆者はすでにエッセイの序論"}))
        next(gen)

    # from lab.mcp import get_virtual_mcp_handler, test_virtual_mcp_handler

    # virtual_mcp_handler = await get_virtual_mcp_handler()
    # await test_virtual_mcp_handler(virtual_mcp_handler)

    yield

    logger.info("Unloading TTS model...")


class WebSocketServer:
    def __init__(self, config: vtuber_config):
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
        self.app.include_router(vtuber_router)
        self.app.include_router(deeplx_router)
        if lab_settings.package.funasr:
            from lab.api.routes.asr import router as asr_router

            self.app.include_router(asr_router)
        if lab_settings.package.gpt_sovits:
            from lab.api.routes.gpt_sovits import router as gsv_router

            self.app.include_router(gsv_router)
            from lab.api.routes.gpt_sovits_v2 import router as gsv_v2_router

            self.app.include_router(gsv_v2_router)

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

    def run(self):
        pass

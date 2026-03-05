from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from lab.api.routes.deeplx import router as deeplx_router
from lab.api.routes.vtuber import init_client_ws_route, router as vtuber_router
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.service_context import ServiceContext

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
    if lab_settings.package.funasr:
        from lab.api.core_logic import load_model

        logger.info("预加载 FunASR 模型...")
        load_model()  # 预加载模型，确保模型在启动时初始化

    if lab_settings.package.gpt_sovits:
        # 应用启动时执行
        # 动态导入合成器模块, 此处可写成 from gsv.Synthesizers.xxx import TTS_Synthesizer, TTS_Task
        from importlib import import_module

        from gsv.gsv_state_manager import (
            gsv_tts_state_manager,  # type: ignore[reportMissingImports,reportUnknownVariableType]
        )

        logger.info("预加载 GPT-SoVITS 模型...")
        synthesizer_name = "gsv_fast"
        synthesizer_module = import_module(f"gsv.Synthesizers.{synthesizer_name}")
        TTS_Synthesizer = synthesizer_module.TTS_Synthesizer
        # TTS_Task = synthesizer_module.TTS_Task
        # 初始化合成器的类
        tts_synthesizer = TTS_Synthesizer(debug_mode=True)
        gsv_tts_state_manager.set_state(tts_synthesizer)  # type: ignore[reportUnknownMemberType]
        # 生成一句话充当测试，减少第一次请求的等待时间
        gen = tts_synthesizer.generate(tts_synthesizer.params_parser({"text": "筆者はすでにエッセイの序論"}))  # type: ignore[reportUnknownMemberType]
        next(gen)

    if lab_settings.package.qwen_tts:
        # 预加载 Qwen3-TTS 模型（避免首次请求慢）
        try:
            from lab.api.logic.qwen_tts_logic import get_logic

            logger.info("预加载 Qwen3-TTS 模型...")
            logic = get_logic()
            # 触发模型加载
            _ = logic.model
            logger.info("✅ Qwen3-TTS 模型预加载完成")
        except Exception as exc:
            logger.warning("⚠️ Qwen3-TTS 预加载失败：%s — /tts/qwen 端点将不可用", exc)

    ctx = getattr(app.state, "default_context_cache", None)
    if ctx is not None and lab_settings.agent.enable_mcp:
        # 尝试连接 MCP 服务器
        try:
            logger.info("Application startup: connecting to MCP servers...")
            await ctx.agent_engine.connect_mcp_servers()
            logger.info("MCP servers connected.")
        except Exception:
            logger.warning("Failed to connect to MCP servers on startup.")
            logger.warning("你可能没开启 MCP Server，先运行 `just mcp-server` 启动 MCP Server。")
            logger.warning(
                "如果你不需要使用工具调用功能，可以忽略此警告。或者将 lab.toml 里的 enable_mcp 设置为 false。"
            )
            logger.warning("继续启动应用，但本次运行工具调用功能将被禁用。")

    # Memory bench router initialisation (配置完全隔离：从 memory_bench/.env.benchmark 加载)
    if lab_settings.package.memory_bench:
        try:
            from memory_bench.server.chat_router import (  # type: ignore[reportMissingImports]
                chat_state,
            )
            from memory_bench.server.router import (  # type: ignore[reportMissingImports]
                state as memory_state,
            )
            from memory_bench.server.startup import (
                init_chat_router_state,  # type: ignore[reportMissingImports]
                init_router_state,  # type: ignore[reportMissingImports]
                load_memory_bench_env,  # type: ignore[reportMissingImports]
                resolve_memory_bench_config,  # type: ignore[reportMissingImports]
            )

            load_memory_bench_env()
            cfg = resolve_memory_bench_config()
            init_router_state(memory_state, cfg)
            init_chat_router_state(chat_state, cfg)
            logger.info("✅ memory_bench router initialized (mounted at /memory)")
            logger.info("✅ memory_bench chat_router initialized (mounted at /memory/chat)")
        except Exception as exc:
            logger.warning("⚠️ memory_bench router init failed: %s — /memory endpoints will be unavailable", exc)

    yield

    logger.info("Application shutdown: lifespan cleanup completed.")


class WebSocketServer:
    def __init__(self):
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
        default_context_cache.load_from_config(default_context_cache.lab_setting)

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
        if lab_settings.package.qwen_tts:
            from lab.api.routes.qwen_tts import router as qwen_tts_router

            self.app.include_router(qwen_tts_router)
        if lab_settings.package.memory_bench:
            from memory_bench.server.chat_router import router as chat_router  # type: ignore[reportMissingImports]
            from memory_bench.server.router import router as memory_router  # type: ignore[reportMissingImports]

            self.app.include_router(memory_router, prefix="/memory")
            self.app.include_router(chat_router, prefix="/memory")

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

        self.app.state.default_context_cache = default_context_cache

    def run(self):
        pass

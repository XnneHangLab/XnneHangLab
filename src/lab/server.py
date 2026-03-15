from __future__ import annotations

import time
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.service_context import ServiceContext

if TYPE_CHECKING:
    from collections.abc import Callable

lab_settings: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)

ROOT_DIR = Path(lab_settings.root.root_dir) / "static"

if not ROOT_DIR.exists():
    raise FileNotFoundError(f"Static root directory {ROOT_DIR} does not exist.")


class CustomStaticFiles(StaticFiles):
    async def get_response(self, path, scope):  # type: ignore[override]
        """为 JavaScript 静态资源补充内容类型。

        Args:
            path: 请求的相对路径。
            scope: Starlette 请求作用域。

        Returns:
            Response: 处理后的响应对象。

        Raises:
            None.
        """
        response = await super().get_response(path, scope)
        if path.endswith(".js"):
            response.headers["Content-Type"] = "application/javascript"
        return response


class AvatarStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):  # type: ignore[override]
        """限制头像目录只允许访问图片资源。

        Args:
            path: 请求的相对路径。
            scope: Starlette 请求作用域。

        Returns:
            Response: 合法图片返回文件响应，否则返回 403。

        Raises:
            None.
        """
        allowed_extensions = (".jpg", ".jpeg", ".png", ".gif", ".svg")
        if not any(path.lower().endswith(ext) for ext in allowed_extensions):
            return Response("Forbidden file type", status_code=403)
        return await super().get_response(path, scope)


def _include_router_with_log(name: str, include: Callable[[], None]) -> None:
    """统一记录路由注册耗时。

    Args:
        name: 路由或初始化阶段名称。
        include: 实际执行注册的回调。

    Returns:
        None.

    Raises:
        None.
    """
    started = time.perf_counter()
    logger.info("⏳ 初始化 {}...", name)
    include()
    logger.info("✅ {} 初始化完成 ({:.1f}s)", name, time.perf_counter() - started)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理 FastAPI 生命周期中的预加载逻辑。

    Args:
        app: FastAPI 应用实例。

    Returns:
        None.

    Raises:
        ValueError: memory_bench 或 `/memory/chat` 缺少关键配置时抛出。
    """
    if lab_settings.package.sherpa_asr:
        from lab.api.logic.sherpa_asr import load_sherpa_asr

        started = time.perf_counter()
        logger.info("⏳ 预加载 Sherpa-ONNX ASR/VAD 引擎...")
        load_sherpa_asr()
        logger.info("✅ Sherpa-ONNX ASR/VAD 预加载完成 ({:.1f}s)", time.perf_counter() - started)

    if lab_settings.package.qwen_asr:
        from lab.api.logic.qwen_asr import preload_configured_qwen_asr_engines

        started = time.perf_counter()
        logger.info("⏳ 预加载 Qwen3-ASR 引擎...")
        loaded_models = preload_configured_qwen_asr_engines()
        if loaded_models:
            logger.info(
                "✅ Qwen3-ASR 引擎预加载完成 ({:.1f}s, models={})",
                time.perf_counter() - started,
                ",".join(loaded_models),
            )
        else:
            logger.warning("Qwen3-ASR service is enabled, but `asr.qwen_asr.preload_models` is empty.")

    if lab_settings.package.qwen_tts:
        from lab.api.logic.faster_qwen_tts import init_qwen_tts_model

        started = time.perf_counter()
        logger.bind(group="tts").info("⏳ 初始化 faster-qwen-tts 后端...")
        init_qwen_tts_model()
        logger.bind(group="tts").info(
            "✅ faster-qwen-tts 后端初始化完成 ({:.1f}s)",
            time.perf_counter() - started,
        )

    if lab_settings.package.gpt_sovits:
        from gsv.gsv_state_manager import (  # type: ignore[reportMissingImports,reportUnknownVariableType]
            gsv_tts_state_manager,
        )

        started = time.perf_counter()
        logger.info("⏳ 初始化 GPT-SoVITS 后端...")
        synthesizer_module = import_module("gsv.Synthesizers.gsv_fast")
        tts_synthesizer = synthesizer_module.TTS_Synthesizer(debug_mode=True)
        gsv_tts_state_manager.set_state(tts_synthesizer)  # type: ignore[reportUnknownMemberType]
        generator = tts_synthesizer.generate(
            tts_synthesizer.params_parser({"text": "签名者ですでにエッセイの序説"})  # type: ignore[reportUnknownMemberType]
        )
        next(generator)
        logger.info("✅ GPT-SoVITS 后端初始化完成 ({:.1f}s)", time.perf_counter() - started)

    ctx = getattr(app.state, "default_context_cache", None)
    if ctx is not None and lab_settings.agent.enable_tool:
        try:
            logger.info("Application startup: connecting to MCP servers...")
            await ctx.agent_engine.connect_mcp_servers()
            logger.info("MCP servers connected.")
        except Exception:
            logger.warning("Failed to connect to MCP servers on startup.")
            logger.warning("You may not have started the MCP server yet. Run `just mcp-server` first.")
            logger.warning("If you do not need tool calling, you can ignore this warning or disable `enable_tool`.")
            logger.warning("Application startup will continue, but tool calling is disabled for this run.")

    if lab_settings.package.memory_bench:
        try:
            started = time.perf_counter()
            logger.info("⏳ 初始化 memory_bench 后端...")
            from memory_bench.server.router import state as memory_state  # type: ignore[reportMissingImports]
            from memory_bench.server.startup import (  # type: ignore[reportMissingImports]
                init_router_state,
                load_memory_bench_env,
                resolve_memory_bench_config,
            )

            memory_bench_cfg = lab_settings.memory_bench
            chat_model_cfg = lab_settings.agent.chat_model
            embedding_cfg = lab_settings.agent.embedding
            chat_llm = getattr(lab_settings.agent.llm, chat_model_cfg.llm_provider)

            missing: list[str] = []
            if not chat_llm.llm_api_key:
                missing.append(f"agent.llm.{chat_model_cfg.llm_provider}.llm_api_key")
            if not embedding_cfg.api_key:
                missing.append("agent.embedding.api_key")
            if missing:
                raise ValueError(f"memory_bench startup is missing required config: {', '.join(missing)}")

            overrides: dict[str, object] = {
                "chat_api_key": chat_llm.llm_api_key,
                "chat_base_url": chat_llm.llm_base_url,
                "chat_model": chat_model_cfg.llm_model_name,
                "llm_api_key": chat_llm.llm_api_key,
                "llm_base_url": chat_llm.llm_base_url,
                "llm_model": chat_model_cfg.llm_model_name,
                "embedding_api_key": embedding_cfg.api_key,
                "embedding_base_url": embedding_cfg.base_url,
                "embedding_model": embedding_cfg.model,
                "search_limit": memory_bench_cfg.search_limit,
                "server_api_key": memory_bench_cfg.server_api_key or None,
            }

            load_memory_bench_env()
            cfg = resolve_memory_bench_config(overrides=overrides)
            init_router_state(memory_state, cfg)
            logger.info(
                "✅ memory_bench 后端初始化完成 ({:.1f}s, upstream={} / {})",
                time.perf_counter() - started,
                cfg["chat_base_url"],
                cfg["chat_model"],
            )

            try:
                chat_started = time.perf_counter()
                logger.info("⏳ 初始化 /memory/chat 端点...")
                from lab.agent.agent_factory import AgentFactory
                from lab.agent.storage import ConversationStoreAdapter
                from lab.api.routes.chat import chat_state
                from lab.conversation.store import ConversationStore

                ws_root = Path(lab_settings.root.root_dir)
                chat_state.chat_model = chat_model_cfg.llm_model_name
                chat_state.workspace_root = str(ws_root)
                chat_state.conversations_dir = str(ws_root / "data" / "conversations")

                chat_profile_path_str = lab_settings.agent.memory_chat_profile
                if not chat_profile_path_str:
                    raise ValueError(
                        'lab_settings.agent.memory_chat_profile is not configured; set it under [agent], for example "profiles/xxx.toml"'
                    )

                chat_profile_path = Path(chat_profile_path_str)
                if not chat_profile_path.is_absolute():
                    chat_profile_path = ws_root / chat_profile_path_str
                if not chat_profile_path.exists():
                    raise FileNotFoundError(f"memory_chat_profile not found: {chat_profile_path}")

                chat_store = ConversationStore(base_dir=chat_state.conversations_dir)
                chat_state.agent_core = await AgentFactory.create_core_with_profile(
                    lab_setting=lab_settings,
                    profile_path=chat_profile_path,
                    storage=ConversationStoreAdapter(chat_store),
                    workspace_root=ws_root,
                    packages=lab_settings.package.to_dict(),
                )
                logger.info(
                    "✅ /memory/chat 端点初始化完成 ({:.1f}s, profile={})",
                    time.perf_counter() - chat_started,
                    chat_profile_path_str,
                )
            except ValueError:
                raise
            except Exception as chat_exc:
                logger.warning("Chat endpoint init failed: {}", chat_exc)

        except ValueError:
            raise
        except Exception as exc:
            logger.warning("memory_bench backend init failed: {} ; backend routes will be unavailable", exc)

    yield

    logger.info("Application shutdown: lifespan cleanup completed.")


class WebSocketServer:
    def __init__(self) -> None:
        """创建并初始化 WebSocket/FastAPI 服务。

        Args:
            None.

        Returns:
            None.

        Raises:
            None.
        """
        self.app = FastAPI(lifespan=lifespan)

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        import asyncio

        default_context_cache = ServiceContext()
        asyncio.run(default_context_cache.load_from_config(default_context_cache.lab_setting))

        _include_router_with_log(
            "/client-ws 端点",
            lambda: self.app.include_router(
                import_module("lab.api.routes.vtuber").init_client_ws_route(
                    default_context_cache=default_context_cache
                ),
            ),
        )
        _include_router_with_log(
            "VTuber 基础端点",
            lambda: self.app.include_router(import_module("lab.api.routes.vtuber").router),
        )
        _include_router_with_log(
            "DeepLX 端点",
            lambda: self.app.include_router(import_module("lab.api.routes.deeplx").router),
        )
        if lab_settings.package.llm_translate:
            _include_router_with_log(
                "LLM Translate 端点",
                lambda: self.app.include_router(import_module("lab.api.routes.llm_translate").router),
            )
        if lab_settings.package.sherpa_asr or lab_settings.package.qwen_asr:
            _include_router_with_log(
                "ASR reload 端点",
                lambda: self.app.include_router(import_module("lab.api.routes.asr_reload").router),
            )
        if lab_settings.package.sherpa_asr:
            _include_router_with_log(
                "Sherpa-ONNX ASR 端点",
                lambda: self.app.include_router(import_module("lab.api.routes.asr_sherpa").router),
            )
        if lab_settings.package.qwen_asr:
            _include_router_with_log(
                "Qwen3-ASR 端点",
                lambda: self.app.include_router(import_module("lab.api.routes.asr_qwen").router),
            )
        if lab_settings.package.qwen_tts:
            _include_router_with_log(
                "faster-qwen-tts 端点",
                lambda: self.app.include_router(import_module("lab.api.routes.faster_qwen_tts").router),
            )
        if lab_settings.package.gpt_sovits:
            _include_router_with_log(
                "GPT-SoVITS 端点",
                lambda: self.app.include_router(import_module("lab.api.routes.gpt_sovits").router),
            )
            _include_router_with_log(
                "GPT-SoVITS v2 端点",
                lambda: self.app.include_router(import_module("lab.api.routes.gpt_sovits_v2").router),
            )
        if lab_settings.package.memory_bench:
            _include_router_with_log(
                "memory_bench 路由",
                lambda: self.app.include_router(
                    import_module("memory_bench.server.router").router,
                    prefix="/memory",
                ),
            )
            _include_router_with_log(
                "/memory/chat 路由",
                lambda: self.app.include_router(
                    import_module("lab.api.routes.chat").chat_router,
                    prefix="/memory",
                ),
            )

        logger.info("Mounting static files from {}", ROOT_DIR)
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
        self.app.mount(
            "/web-tool",
            CustomStaticFiles(directory=str(ROOT_DIR / "web_tool"), html=True),
            name="web_tool",
        )

        self.app.state.default_context_cache = default_context_cache

    def run(self) -> None:
        """预留运行入口。

        Args:
            None.

        Returns:
            None.

        Raises:
            None.
        """
        pass

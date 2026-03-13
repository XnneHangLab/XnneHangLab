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


def _include_router_with_log(name: str, include: Callable[[], None]) -> None:
    """以统一格式记录路由初始化和注册耗时。

    Args:
        name: 日志中展示的路由或初始化项名称。
        include: 实际执行路由注册的无参回调。

    Returns:
        None.
    """
    t = time.perf_counter()
    logger.info("⏳ 初始化 {}...", name)
    include()
    logger.info("✅ {} 初始化完成 ({:.1f}s)", name, time.perf_counter() - t)


# 应用生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理 FastAPI 生命周期内的预加载与启动初始化流程。

    启动阶段会根据 package 开关依次初始化 ASR、TTS、GPT-SoVITS、
    memory_bench 与 `/memory/chat`，并为每个阶段输出开始和结束耗时日志。

    Args:
        app: 当前 FastAPI 应用实例。

    Returns:
        AsyncIterator[None]: 提供给 FastAPI 的生命周期上下文。

    Raises:
        ValueError: memory_bench 或 `/memory/chat` 缺少必需配置时抛出。
    """
    if lab_settings.package.funasr:
        from lab.api.logic import load_funasr

        logger.info("预加载 FunASR 模型...")
        t = time.perf_counter()
        logger.info("⏳ 初始化 ASR（FunASR）后端...")
        load_funasr()
        logger.info("✅ ASR（FunASR）后端初始化完成 ({:.1f}s)", time.perf_counter() - t)

    if lab_settings.package.whisper:
        from lab.api.logic import load_whisper

        logger.info("预加载 Whisper 模型...")
        t = time.perf_counter()
        logger.info("⏳ 初始化 ASR（Whisper）后端...")
        load_whisper()
        logger.info("✅ ASR（Whisper）后端初始化完成 ({:.1f}s)", time.perf_counter() - t)

    if lab_settings.package.qwen_tts:
        from lab.api.logic.faster_qwen_tts import init_qwen_tts_model

        logger.bind(group="tts").info("预加载 faster-qwen-tts 模型...")
        t = time.perf_counter()
        logger.bind(group="tts").info("⏳ 初始化 TTS（faster-qwen-tts）后端...")
        init_qwen_tts_model()
        logger.bind(group="tts").info("✅ TTS（faster-qwen-tts）后端初始化完成 ({:.1f}s)", time.perf_counter() - t)

    if lab_settings.package.gpt_sovits:
        # 应用启动时执行
        # 动态导入合成器模块, 此处可写成 from gsv.Synthesizers.xxx import TTS_Synthesizer, TTS_Task
        from importlib import import_module

        from gsv.gsv_state_manager import (
            gsv_tts_state_manager,  # type: ignore[reportMissingImports,reportUnknownVariableType]
        )

        logger.info("预加载 GPT-SoVITS 模型...")
        t = time.perf_counter()
        logger.info("⏳ 初始化 GPT-SoVITS 后端...")
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
        logger.info("✅ GPT-SoVITS 后端初始化完成 ({:.1f}s)", time.perf_counter() - t)

    ctx = getattr(app.state, "default_context_cache", None)
    if ctx is not None and lab_settings.agent.enable_tool:
        # 尝试连接 MCP 服务器
        try:
            logger.info("Application startup: connecting to MCP servers...")
            await ctx.agent_engine.connect_mcp_servers()
            logger.info("MCP servers connected.")
        except Exception:
            logger.warning("Failed to connect to MCP servers on startup.")
            logger.warning("你可能没开启 MCP Server，先运行 `just mcp-server` 启动 MCP Server。")
            logger.warning(
                "如果你不需要使用工具调用功能，可以忽略此警告。或者将 lab.toml 里的 enable_tool 设置为 false。"
            )
            logger.warning("继续启动应用，但本次运行工具调用功能将被禁用。")

    # Memory bench backend initialisation
    # 配置优先级：lab.toml > memory_bench/.env.benchmark
    if lab_settings.package.memory_bench:
        try:
            t = time.perf_counter()
            logger.info("⏳ 初始化 memory_bench 后端...")
            from memory_bench.server.router import (  # type: ignore[reportMissingImports]
                state as memory_state,
            )
            from memory_bench.server.startup import (
                init_router_state,  # type: ignore[reportMissingImports]
                load_memory_bench_env,  # type: ignore[reportMissingImports]
                resolve_memory_bench_config,  # type: ignore[reportMissingImports]
            )

            memory_bench_cfg = lab_settings.memory_bench
            chat_model_cfg = lab_settings.agent.chat_model
            embedding_cfg = lab_settings.agent.embedding
            chat_llm = getattr(lab_settings.agent.llm, chat_model_cfg.llm_provider)

            # 必填校验：缺配置直接报错，不静默失败
            missing: list[str] = []
            if not chat_llm.llm_api_key:
                missing.append(f"agent.llm.{chat_model_cfg.llm_provider}.llm_api_key")
            if not embedding_cfg.api_key:
                missing.append("agent.embedding.api_key")
            if missing:
                raise ValueError(f"memory_bench startup is missing required config: {', '.join(missing)}")

            overrides: dict[str, object] = {
                # proxy 上游转发目标
                "chat_api_key": chat_llm.llm_api_key,
                "chat_base_url": chat_llm.llm_base_url,
                "chat_model": chat_model_cfg.llm_model_name,
                # mem0 事实提取 LLM：直接复用 chat_model（无 fallback 链）
                "llm_api_key": chat_llm.llm_api_key,
                "llm_base_url": chat_llm.llm_base_url,
                "llm_model": chat_model_cfg.llm_model_name,
                # embedding：来自 agent.embedding
                "embedding_api_key": embedding_cfg.api_key,
                "embedding_base_url": embedding_cfg.base_url,
                "embedding_model": embedding_cfg.model,
                # 检索参数
                "search_limit": memory_bench_cfg.search_limit,
                "server_api_key": memory_bench_cfg.server_api_key or None,
            }

            load_memory_bench_env()
            cfg = resolve_memory_bench_config(overrides=overrides)
            init_router_state(memory_state, cfg)
            logger.info(
                "✅ memory_bench 后端初始化完成 ({:.1f}s, upstream={} / {})",
                time.perf_counter() - t,
                cfg["chat_base_url"],
                cfg["chat_model"],
            )
            logger.info(
                "✅ memory_bench backend initialized (upstream={} / {})",
                cfg["chat_base_url"],
                cfg["chat_model"],
            )

            # --- Chat endpoint (src/lab) ---
            # AgentCore handles everything: LLM, tools, prompt, storage.
            try:
                t = time.perf_counter()
                logger.info("⏳ 初始化 /memory/chat 端点...")
                from lab.agent.agent_factory import AgentFactory
                from lab.agent.storage import ConversationStoreAdapter
                from lab.api.routes.chat import chat_state
                from lab.conversation.store import ConversationStore

                ws_root = Path(lab_settings.root.root_dir)
                chat_state.chat_model = chat_model_cfg.llm_model_name
                chat_state.workspace_root = str(ws_root)
                chat_state.conversations_dir = str(ws_root / "data" / "conversations")

                _chat_profile_path_str = lab_settings.agent.memory_chat_profile
                if not _chat_profile_path_str:
                    raise ValueError(
                        "lab_settings.agent.memory_chat_profile 未配置，"
                        '请在 lab.toml 的 [agent] 下设置 memory_chat_profile = "profiles/xxx.toml"'
                    )
                _chat_profile_path = Path(_chat_profile_path_str)
                if not _chat_profile_path.is_absolute():
                    _chat_profile_path = ws_root / _chat_profile_path_str
                if not _chat_profile_path.exists():
                    raise FileNotFoundError(f"memory_chat_profile not found: {_chat_profile_path}")

                chat_store = ConversationStore(base_dir=chat_state.conversations_dir)
                chat_state.agent_core = await AgentFactory.create_core_with_profile(
                    lab_setting=lab_settings,
                    profile_path=_chat_profile_path,
                    storage=ConversationStoreAdapter(chat_store),
                    workspace_root=ws_root,
                    packages=lab_settings.package.to_dict(),
                )
                logger.info("✅ Chat endpoint initialized (AgentCore, profile={})", _chat_profile_path_str)
                logger.info(
                    "✅ /memory/chat 端点初始化完成 ({:.1f}s, profile={})",
                    time.perf_counter() - t,
                    _chat_profile_path_str,
                )
            except ValueError:
                raise
            except Exception as chat_exc:
                logger.warning("⚠️ Chat endpoint init failed: %s", chat_exc)

        except ValueError:
            raise
        except Exception as exc:
            logger.warning("⚠️ memory_bench backend init failed: %s — backend routes will be unavailable", exc)

    yield

    logger.info("Application shutdown: lifespan cleanup completed.")


class WebSocketServer:
    def __init__(self):
        """创建并初始化 WebSocket Server 与已启用的路由。

        可选功能对应的路由会根据 `package.*` 开关按需导入，避免在启动早期
        为未启用能力加载重量级依赖。

        Returns:
            None.
        """
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
        import asyncio

        default_context_cache = ServiceContext()
        asyncio.run(default_context_cache.load_from_config(default_context_cache.lab_setting))

        # Include routes
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
        if lab_settings.package.funasr or lab_settings.package.whisper:
            _include_router_with_log(
                "ASR 端点",
                lambda: self.app.include_router(import_module("lab.api.routes.asr").router),
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
            )  # /memory/chat  /memory/sessions  /memory/chat/health
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

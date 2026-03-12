from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from lab.api.routes.deeplx import router as deeplx_router
from lab.api.routes.faster_qwen_tts import router as qwen_tts_router
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
        from lab.api.logic import load_funasr

        logger.info("预加载 FunASR 模型...")
        load_funasr()

    if lab_settings.package.whisper:
        from lab.api.logic import load_whisper

        logger.info("预加载 Whisper 模型...")
        load_whisper()

    if lab_settings.package.qwen_tts:
        from lab.api.logic.faster_qwen_tts import init_qwen_tts_model

        logger.bind(group="tts").info("预加载 faster-qwen-tts 模型...")
        init_qwen_tts_model()

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

    # Memory bench proxy_router initialisation
    # 配置优先级：lab.toml > memory_bench/.env.benchmark
    if lab_settings.package.memory_bench:
        try:
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
            # upstream_llm_provider 显式指定真实上游，与 chat_model.llm_provider 职责分离
            # （chat_model 此时指向 memory_bench 自身，直接读会回环）
            upstream_llm = getattr(lab_settings.agent.llm, memory_bench_cfg.upstream_llm_provider)

            # 必填校验：缺配置直接报错，不静默失败
            missing: list[str] = []
            if not upstream_llm.llm_api_key:
                missing.append(f"agent.llm.{memory_bench_cfg.upstream_llm_provider}.llm_api_key")
            if not embedding_cfg.api_key:
                missing.append("agent.embedding.api_key")
            if missing:
                raise ValueError(f"memory_bench 启动缺少必填配置：{', '.join(missing)}")

            overrides: dict[str, object] = {
                # proxy 上游转发目标
                "chat_api_key": upstream_llm.llm_api_key,
                "chat_base_url": upstream_llm.llm_base_url,
                "chat_model": chat_model_cfg.llm_model_name,
                # mem0 事实提取 LLM：直接复用 chat_model（无 fallback 链）
                "llm_api_key": upstream_llm.llm_api_key,
                "llm_base_url": upstream_llm.llm_base_url,
                "llm_model": chat_model_cfg.llm_model_name,
                # embedding：来自 agent.embedding
                "embedding_api_key": embedding_cfg.api_key,
                "embedding_base_url": embedding_cfg.base_url,
                "embedding_model": embedding_cfg.model,
                # 检索参数
                "user_id": memory_bench_cfg.user_id,
                "agent_id": memory_bench_cfg.agent_id,
                "search_limit": memory_bench_cfg.search_limit,
                "server_api_key": memory_bench_cfg.server_api_key or None,
            }

            load_memory_bench_env()
            cfg = resolve_memory_bench_config(overrides=overrides)
            init_router_state(memory_state, cfg)
            logger.info(
                "✅ memory_bench proxy_router initialized (upstream→{} / {})",
                cfg["chat_base_url"],
                cfg["chat_model"],
            )

            # --- Chat endpoint (src/lab) ---
            # Uses ToolManager + AsyncLLM, imports memory functions from memory_bench
            try:
                from lab.agent.agent_factory import AgentFactory, build_default_tool_manager
                from lab.agent.stateless_llm_factory import LLMFactory
                from lab.agent.storage import ConversationStoreAdapter
                from lab.api.routes.chat import chat_state
                from lab.conversation.store import ConversationStore
                from lab.plugin.loader import PluginLoader
                from lab.profile.context_injector import ContextInjector
                from lab.profile.schema import Profile
                from lab.tools import AgentContext

                ws_root = Path(lab_settings.root.root_dir)
                agent_context = AgentContext(workspace_root=ws_root)

                chat_llm_instance = LLMFactory.create_llm(
                    model=chat_model_cfg.llm_model_name,
                    base_url=upstream_llm.llm_base_url,
                    llm_api_key=upstream_llm.llm_api_key,
                )

                chat_state.chat_llm = chat_llm_instance
                chat_state.agent_context = agent_context
                chat_state.chat_model = chat_model_cfg.llm_model_name
                chat_state.workspace_root = str(ws_root)

                _profile_setting = lab_settings.agent.memory_chat_profile or "profiles/congyin.toml"
                _profile_path = Path(_profile_setting)
                if not _profile_path.is_absolute():
                    _profile_path = ws_root / _profile_setting
                if not _profile_path.exists():
                    raise FileNotFoundError(f"Profile not found: {_profile_path}")
                _profile = Profile.from_toml(_profile_path)
                chat_state.profile = _profile
                chat_state.context_injector = ContextInjector(_profile.context)
                logger.info("✅ Chat profile loaded: {}", _profile.profile.name)

                # Load plugins declared in profile
                plugin_loader = PluginLoader()
                tool_plugins, skill_descriptors = await plugin_loader.load_many(
                    _profile.plugins.enabled,
                    profile_overrides=_profile.plugins.overrides,
                    ctx=agent_context,
                )
                tool_manager = build_default_tool_manager(ws_root)
                for tp in tool_plugins:
                    for bt in tp.get_tools():
                        tool_manager.register_builtin(bt)
                chat_state.tool_manager = tool_manager
                chat_state.skill_descriptors = skill_descriptors
                logger.info(
                    "✅ Plugins loaded: {} tools, {} skills",
                    len(tool_plugins),
                    len(skill_descriptors),
                )

                chat_state.conversations_dir = str(ws_root / "data" / "conversations")

                _chat_profile_path_str = lab_settings.agent.memory_chat_profile
                if _chat_profile_path_str:
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
                    )
                    logger.info("✅ AgentCore initialized with profile: {}", _chat_profile_path_str)

                logger.info(
                    "✅ Chat endpoint initialized (model={}, tools={})",
                    chat_state.chat_model,
                    len(tool_manager.list_tools_schema()),
                )
            except Exception as chat_exc:
                logger.warning("⚠️ Chat endpoint init failed: %s", chat_exc)

        except Exception as exc:
            logger.warning("⚠️ memory_bench router init failed: %s — proxy_router will be unavailable", exc)

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
        import asyncio

        default_context_cache = ServiceContext()
        asyncio.run(default_context_cache.load_from_config(default_context_cache.lab_setting))

        # Include routes
        self.app.include_router(
            init_client_ws_route(default_context_cache=default_context_cache),
        )
        self.app.include_router(vtuber_router)
        self.app.include_router(deeplx_router)
        if lab_settings.package.funasr or lab_settings.package.whisper:
            from lab.api.routes.asr import router as asr_router

            self.app.include_router(asr_router)
        if lab_settings.package.qwen_tts:
            self.app.include_router(qwen_tts_router)
        if lab_settings.package.gpt_sovits:
            from lab.api.routes.gpt_sovits import router as gsv_router

            self.app.include_router(gsv_router)
            from lab.api.routes.gpt_sovits_v2 import router as gsv_v2_router

            self.app.include_router(gsv_v2_router)
        if lab_settings.package.memory_bench:
            from memory_bench.server.proxy_router import proxy_router  # type: ignore[reportMissingImports]

            self.app.include_router(proxy_router)  # /v1/chat/completions  /v1/models  /health

            from lab.api.routes.chat import chat_router

            self.app.include_router(
                chat_router, prefix="/memory"
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

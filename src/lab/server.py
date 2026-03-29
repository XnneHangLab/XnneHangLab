from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from functools import partial
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from tqdm import tqdm

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.profile.schema import Profile
from lab.service_context import ServiceContext

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from loguru import Logger

lab_settings: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)
_tts_logger = logger.bind(group="tts")

_T = TypeVar("_T")

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
        if path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
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


async def _run_blocking(func: Callable[[], _T]) -> _T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func)


async def _run_startup_step(
    start_message: str,
    func: Callable[[], _T],
    *,
    success_message: str | None = None,
    success_handler: Callable[[Logger, float, _T], None] | None = None,
    step_logger: Logger = logger,
) -> _T:
    started = time.perf_counter()
    step_logger.info(start_message)
    result = await _run_blocking(func)
    elapsed = time.perf_counter() - started
    if success_handler is not None:
        success_handler(step_logger, elapsed, result)
    elif success_message is not None:
        step_logger.info(success_message, elapsed)
    return result


def _log_qwen_asr_startup_result(step_logger: Logger, elapsed: float, loaded_models: Sequence[str]) -> None:
    if loaded_models:
        step_logger.info(f"✅ Qwen3-ASR 引擎预加载完成 ({elapsed:.1f}s, models={','.join(loaded_models)})")
    else:
        step_logger.warning("Qwen3-ASR service is enabled, but `asr.qwen_asr.preload_models` is empty.")


def _log_llm_translate_startup_result(step_logger: Logger, elapsed: float, loaded: bool) -> None:
    if loaded:
        step_logger.info(f"✅ LLM Translate 后端初始化完成 ({elapsed:.1f}s)")
    else:
        step_logger.warning("LLM Translate service is enabled, but `agent.translate.llm.model_path` is empty.")


def _resolve_profile_path(settings: XnneHangLabSettings, profile_path_str: str) -> Path:
    profile_path = Path(profile_path_str)
    if not profile_path.is_absolute():
        profile_path = Path(settings.root.root_dir) / profile_path
    return profile_path


def _resolve_active_gpt_sovits_character(settings: XnneHangLabSettings) -> str | None:
    profile_path_str = settings.agent.memory_agent_profile
    if not profile_path_str:
        return None

    profile_path = _resolve_profile_path(settings, profile_path_str)
    if not profile_path.exists():
        return None

    try:
        profile = Profile.from_toml(profile_path)
    except Exception:
        return None

    if profile.character is None:
        return None

    if profile.character.tts.character_name.strip():
        return profile.character.tts.character_name.strip()
    if profile.character.character_name.strip():
        return profile.character.character_name.strip()
    if profile.profile.name.strip():
        return profile.profile.name.strip()
    return None


def _init_gpt_sovits_backend() -> None:
    """Initialize GPT-SoVITS into a startup-ready backend state.

    This startup hook imports the GPT-SoVITS modules, constructs the
    synthesizer, stores it in the shared state manager, and performs a
    startup warmup so the first-request cost is paid during startup.
    """
    _tts_logger.info("[GSV init] enter backend initialization")
    try:
        _tts_logger.info("[GSV init] import state manager start")
        from gsv.gsv_state_manager import (  # type: ignore[reportMissingImports,reportUnknownVariableType]
            gsv_tts_state_manager,
        )

        _tts_logger.info("[GSV init] import state manager done")
        _tts_logger.info("[GSV init] import synthesizer module start")
        synthesizer_module = import_module("gsv.Synthesizers.gsv_fast")
        _tts_logger.info("[GSV init] import synthesizer module done")
        active_character = _resolve_active_gpt_sovits_character(lab_settings)
        if not active_character:
            raise ValueError(
                "Failed to resolve GPT-SoVITS character from active profile; "
                "set [character.tts].character_name in the active memory_agent_profile."
            )
        _tts_logger.info(f"[GSV init] resolved active profile character ({active_character})")
        _tts_logger.info("[GSV init] construct TTS_Synthesizer start")
        tts_synthesizer = synthesizer_module.TTS_Synthesizer(
            debug_mode=True,
            default_character=active_character,
        )
        _tts_logger.info("[GSV init] construct TTS_Synthesizer done")
        _tts_logger.info(f"[GSV init] force load active character start ({active_character})")
        tts_synthesizer.load_character(active_character)  # type: ignore[reportUnknownMemberType]
        _tts_logger.info(f"[GSV init] force load active character done ({active_character})")
        _tts_logger.info("[GSV init] set shared state")
        gsv_tts_state_manager.set_state(tts_synthesizer)  # type: ignore[reportUnknownMemberType]
        _tts_logger.info("[GSV init] shared state registered")

        warmup_character = (
            active_character
            or getattr(tts_synthesizer, "character", None)
            or getattr(
                tts_synthesizer,
                "default_character",
                None,
            )
        )
        if not warmup_character:
            raise ValueError("No GPT-SoVITS character available for startup warmup")
        warmup_bar = tqdm(total=4, desc="GSV warmup", leave=False)
        try:
            _tts_logger.info("[GSV init] build warmup params")
            warmup_task = tts_synthesizer.params_parser(  # type: ignore[reportUnknownMemberType]
                {
                    "task_type": "text",
                    "text": "系统预热。",
                    "text_language": "zh",
                    "character": warmup_character,
                    "stream": False,
                }
            )
            _tts_logger.debug(f"[GSV init] warmup task={warmup_task}")
            warmup_bar.update(1)
            warmup_bar.set_postfix_str("params")

            _tts_logger.info("[GSV init] create warmup generator")
            warmup_gen = tts_synthesizer.generate(  # type: ignore[reportUnknownMemberType]
                warmup_task,
                return_type="numpy",
            )
            warmup_bar.update(1)
            warmup_bar.set_postfix_str("generator")
            try:
                _tts_logger.info("[GSV init] advance warmup generator via next(gen)")
                sample_rate, audio_data = next(warmup_gen)
                warmup_bar.update(1)
                warmup_bar.set_postfix_str("first-yield")
                _tts_logger.info("[GSV init] warmup first chunk reached")
                _tts_logger.debug(
                    f"[GSV init] warmup first chunk details sample_rate={sample_rate} samples={len(audio_data)}"
                )
            finally:
                close = getattr(warmup_gen, "close", None)
                if callable(close):
                    close()

            _tts_logger.info("[GSV init] warmup done")
            warmup_bar.update(1)
            warmup_bar.set_postfix_str("done")
        finally:
            warmup_bar.close()
    except Exception:
        _tts_logger.exception("[GSV init] backend initialization failed")
        raise


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

        await _run_startup_step(
            "Preloading Sherpa-ONNX ASR/VAD engines...",
            load_sherpa_asr,
            success_message="Sherpa-ONNX ASR/VAD preload finished ({:.1f}s)",
        )

    if lab_settings.package.qwen_asr:
        from lab.api.logic.qwen_asr import preload_configured_qwen_asr_engines

        await _run_startup_step(
            "Preloading Qwen3-ASR engines...",
            preload_configured_qwen_asr_engines,
            success_handler=_log_qwen_asr_startup_result,
        )

    if lab_settings.package.qwen_tts:
        from lab.api.logic.faster_qwen_tts import load_qwen_tts_model

        await _run_startup_step(
            "Loading Qwen-TTS model...",
            load_qwen_tts_model,
            success_message="Qwen-TTS model loaded and warmed up ({:.1f}s)",
            step_logger=logger.bind(group="tts"),
        )

    if lab_settings.package.llm_translate:
        from lab.api.logic.llm_translate import preload_configured_llm_translate_engine

        await _run_startup_step(
            "⏳ 初始化 LLM Translate 后端...",
            preload_configured_llm_translate_engine,
            success_handler=_log_llm_translate_startup_result,
        )

    if lab_settings.package.local_embedding:
        from lab.api.logic.embedding import load_embedding_model

        await _run_startup_step(
            "⏳ 预加载本地 Embedding 模型...",
            partial(
                load_embedding_model,
                model_path=lab_settings.local_embedding.model_path,
                pooling_type=lab_settings.local_embedding.pooling_type,
                n_gpu_layers=lab_settings.local_embedding.n_gpu_layers,
            ),
            success_message="✅ 本地 Embedding 模型预加载完成 ({:.1f}s)",
        )

    if lab_settings.package.gpt_sovits:
        await _run_startup_step(
            "⏳ 初始化 GPT-SoVITS 后端...",
            _init_gpt_sovits_backend,
            success_message="✅ GPT-SoVITS 后端初始化完成 ({:.1f}s)",
        )

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
            chat_llm = lab_settings.agent.llm.get_provider_config(chat_model_cfg.llm_provider)
            embedding_base_url = f"http://localhost:{lab_settings.server.port}/v1"

            missing: list[str] = []
            if not chat_llm.llm_api_key:
                missing.append(f"agent.llm.{chat_model_cfg.llm_provider}.llm_api_key")
            if not lab_settings.package.local_embedding:
                missing.append("package.local_embedding")
            if missing:
                raise ValueError(f"memory_bench startup is missing required config: {', '.join(missing)}")

            overrides: dict[str, object] = {
                "chat_api_key": chat_llm.llm_api_key,
                "chat_base_url": chat_llm.llm_base_url,
                "chat_model": chat_model_cfg.llm_model_name,
                "llm_api_key": chat_llm.llm_api_key,
                "llm_base_url": chat_llm.llm_base_url,
                "llm_model": chat_model_cfg.llm_model_name,
                "embedding_api_key": "no-key",
                "embedding_base_url": embedding_base_url,
                "embedding_model": "bge-m3",
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
                from lab.agent.storage import HistoryStorageAdapter
                from lab.api.routes.chat import chat_state
                from lab.history_storage.store import HistoryStorage

                ws_root = Path(lab_settings.root.root_dir)
                chat_state.chat_model = chat_model_cfg.llm_model_name
                chat_state.workspace_root = str(ws_root)
                chat_state.history_storage_dir = str(ws_root / "data" / "conversations")

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

                chat_store = HistoryStorage(base_dir=chat_state.history_storage_dir)
                chat_state.agent_core = await AgentFactory.create_core_with_profile(
                    lab_setting=lab_settings,
                    profile_path=chat_profile_path,
                    storage=HistoryStorageAdapter(
                        chat_store,
                        condense_after_turns=lab_settings.agent.structured_history_full_turns,
                    ),
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

    if lab_settings.package.llm_translate:
        from lab.api.logic.llm_translate import unload_llm_translate_engine

        try:
            unload_llm_translate_engine()
        except Exception as exc:
            logger.warning("LLM Translate cleanup failed: {}", exc)

    if lab_settings.package.local_embedding:
        from lab.api.logic.embedding import unload_embedding_model

        try:
            unload_embedding_model()
        except Exception as exc:
            logger.warning("Local embedding cleanup failed: {}", exc)

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

        default_context_cache = ServiceContext()
        asyncio.run(default_context_cache.load_from_config(default_context_cache.lab_setting))
        vtuber_routes = import_module("lab.api.routes.vtuber")
        client_ws_router = vtuber_routes.init_client_ws_route(default_context_cache=default_context_cache)

        _include_router_with_log(
            "/client-ws 端点",
            lambda: self.app.include_router(client_ws_router),
        )
        _include_router_with_log(
            "VTuber 基础端点",
            lambda: self.app.include_router(vtuber_routes.router),
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
        if lab_settings.package.local_embedding:
            _include_router_with_log(
                "本地 Embedding 端点",
                lambda: self.app.include_router(import_module("lab.api.routes.embedding").router),
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

        _include_router_with_log(
            "Admin 管理端点",
            lambda: self.app.include_router(
                import_module("lab.api.routes.admin").router,
                prefix="/admin",
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
        self.app.state.ws_handler = getattr(client_ws_router, "ws_handler", None)

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

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path
from typing import Any, cast

import tomli
import uvicorn
from loguru import logger

from lab.config_manager import LLMSetting, XnneHangLabSettings, load_settings_file

os.environ["HF_HOME"] = str(Path(__file__).parent / "models")
os.environ["MODELSCOPE_CACHE"] = str(Path(__file__).parent / "models")


def get_version() -> str:
    with Path("pyproject.toml").open("rb") as f:
        pyproject = tomli.load(f)
    return pyproject["project"]["version"]


def parse_args(lab_settings: XnneHangLabSettings):
    parser = argparse.ArgumentParser(description="XnneHangLab Server")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--port", type=int, default=lab_settings.server.port, help="Server port")
    return parser.parse_args()


def validate_config(settings: XnneHangLabSettings) -> None:
    """Validate critical runtime configuration before starting the server."""

    errors: list[str] = []

    chat_provider = settings.agent.chat_model.llm_provider
    llm_cfg = cast("LLMSetting | None", getattr(settings.agent.llm, chat_provider, None))
    if llm_cfg is not None and not llm_cfg.llm_api_key:
        errors.append(
            f"  [agent.llm.{chat_provider}]\n"
            "    llm_api_key 未配置\n"
            f"    -> 在 lab.toml 的 [agent.llm.{chat_provider}] 下设置 llm_api_key"
        )

    ws_root = Path(settings.root.root_dir)

    memory_agent_profile = settings.agent.memory_agent_profile
    if memory_agent_profile:
        profile_path = Path(memory_agent_profile)
        if not profile_path.is_absolute():
            profile_path = ws_root / memory_agent_profile
        if not profile_path.exists():
            errors.append(f"  [agent.memory_agent_profile]\n    文件不存在: {profile_path}\n    -> 检查路径是否正确")
        else:
            try:
                with profile_path.open("rb") as f:
                    profile_data: dict[str, Any] = tomllib.load(f)
                enabled_plugins: list[str] = []
                plugins = cast("dict[str, Any] | None", profile_data.get("plugins"))
                if isinstance(plugins, dict):
                    raw_enabled_plugins = plugins.get("enabled")
                    if isinstance(raw_enabled_plugins, list):
                        for plugin in cast("list[Any]", raw_enabled_plugins):
                            if isinstance(plugin, str):
                                enabled_plugins.append(plugin)
                if "memory" in enabled_plugins and not settings.package.memory_bench:
                    errors.append(
                        "  [package]\n"
                        f"    profile '{memory_agent_profile}' 启用了 memory 插件，但 memory_bench = false\n"
                        "    -> 在 lab.toml 的 [package] 下设置 memory_bench = true"
                    )
            except Exception:
                pass

    memory_chat_profile = settings.agent.memory_chat_profile
    if memory_chat_profile:
        chat_profile_path = Path(memory_chat_profile)
        if not chat_profile_path.is_absolute():
            chat_profile_path = ws_root / memory_chat_profile
        if not chat_profile_path.exists():
            errors.append(
                f"  [agent.memory_chat_profile]\n    文件不存在: {chat_profile_path}\n    -> 检查路径是否正确"
            )

    from lab.api.logic.embedding import resolve_embedding_model_path
    from lab.api.logic.llm_translate import resolve_llm_translate_model_path

    translate_provider = settings.agent.translate_provider
    deeplx_api_key = settings.agent.translate.deeplx.api_key.strip()
    llm_translate_enabled = settings.package.llm_translate
    llm_translate_model_path = resolve_llm_translate_model_path(settings)
    llm_translate_model_exists = llm_translate_model_path is not None and llm_translate_model_path.exists()

    if translate_provider == "deeplx" and not deeplx_api_key:
        errors.append(
            "  [translate]\n"
            "    当前翻译 provider 为 deeplx，但 api_key 为空\n"
            '    -> 配置 [agent.translate.deeplx].api_key，或将 [agent].translate_provider 改为 "llm"'
        )

    if translate_provider == "llm" and (not llm_translate_enabled or not llm_translate_model_exists):
        configured_model_text = (
            str(llm_translate_model_path)
            if llm_translate_model_path is not None
            else "<agent.translate.llm.model_path is empty>"
        )
        errors.append(
            "  [translate]\n"
            "    当前翻译 provider 为 llm，但本地翻译后端不可用\n"
            f"    package.llm_translate = {llm_translate_enabled}\n"
            f"    当前 llm model path: {configured_model_text}\n"
            f"    本地 GGUF 是否存在: {llm_translate_model_exists}\n"
            "    -> 将 [package].llm_translate 设为 true，并设置有效的 [agent.translate.llm].model_path，"
            "或运行 `just install-llm-translate`，"
            '或将 [agent].translate_provider 改为 "deeplx" 并配置 key'
        )

    local_embedding_model_path = resolve_embedding_model_path(settings)
    local_embedding_model_exists = local_embedding_model_path is not None and local_embedding_model_path.exists()
    local_embedding_path_text = (
        str(local_embedding_model_path)
        if local_embedding_model_path is not None
        else "<local_embedding.model_path is empty>"
    )

    if settings.package.local_embedding and not local_embedding_model_exists:
        errors.append(
            "  [local_embedding]\n"
            "    本地 Embedding 服务已启用，但 GGUF 模型不可用\n"
            f"    当前 model path: {local_embedding_path_text}\n"
            f"    本地 GGUF 是否存在: {local_embedding_model_exists}\n"
            "    -> 设置有效的 [local_embedding].model_path，或运行 `just download-local-embedding`"
        )

    if settings.package.memory_bench and not settings.package.local_embedding:
        errors.append(
            "  [package]\n"
            "    memory_bench = true，但 local_embedding = false\n"
            "    -> memory_bench 现在依赖本地 Embedding 服务，请在 [package] 下设置 local_embedding = true"
        )
    elif settings.package.memory_bench and not local_embedding_model_exists:
        errors.append(
            "  [memory_bench]\n"
            "    memory_bench 依赖本地 Embedding 模型，但当前模型文件不存在\n"
            f"    当前 model path: {local_embedding_path_text}\n"
            "    -> 先下载模型，再启动 memory_bench"
        )

    if errors:
        logger.error("❌ 配置校验失败，请修复以下问题后重启：\n\n{}", "\n\n".join(errors))
        sys.exit(1)

    logger.info("✅ 配置校验通过")


@logger.catch
def run(lab_settings: XnneHangLabSettings, args: argparse.Namespace):
    """Initialize logging and start the FastAPI server."""

    import lab.server as lab_server_module
    from lab.logger.logger_group import init_logger
    from lab.server import WebSocketServer

    init_logger()
    validate_config(lab_settings)
    logger.info(f"XnneHangLab, version v{get_version()}")

    server_config = lab_settings.server
    if args.port is not None:
        server_config.port = args.port
        lab_server_module.lab_settings.server.port = args.port

    server = WebSocketServer()

    uvicorn.run(
        app=server.app,
        host=server_config.host,
        port=server_config.port,
        log_level=server_config.uvicorn_log_level.lower(),
        ws="websockets-sansio",
    )


if __name__ == "__main__":
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    args = parse_args(lab_settings)

    run(lab_settings=lab_settings, args=args)

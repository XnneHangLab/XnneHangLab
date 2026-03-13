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
    """启动前静态校验配置项，发现问题一次性报出后退出。

    检查范围包括当前 Chat LLM provider 的 `llm_api_key`、embedding
    `api_key`、memory profile 文件存在性，以及 memory 插件和
    `package.memory_bench` 的一致性。

    Args:
        settings: 从 `lab.toml` 加载的完整实验室配置对象。

    Returns:
        None.

    Raises:
        SystemExit: 发现任意配置问题时，记录所有错误并以退出码 1 终止启动。
    """
    errors: list[str] = []

    chat_provider = settings.agent.chat_model.llm_provider
    llm_cfg = cast("LLMSetting | None", getattr(settings.agent.llm, chat_provider, None))
    if llm_cfg is not None and not llm_cfg.llm_api_key:
        errors.append(
            f"  [agent.llm.{chat_provider}]\n"
            "    llm_api_key 未配置\n"
            f"    → 在 lab.toml 的 [agent.llm.{chat_provider}] 下设置 llm_api_key"
        )

    if not settings.agent.embedding.api_key:
        errors.append(
            "  [agent.embedding]\n"
            "    api_key 未配置\n"
            "    → 在 lab.toml 的 [agent.embedding] 下设置 api_key"
        )

    ws_root = Path(settings.root.root_dir)

    memory_agent_profile = settings.agent.memory_agent_profile
    if memory_agent_profile:
        profile_path = Path(memory_agent_profile)
        if not profile_path.is_absolute():
            profile_path = ws_root / memory_agent_profile
        if not profile_path.exists():
            errors.append(
                f"  [agent.memory_agent_profile]\n"
                f"    文件不存在: {profile_path}\n"
                "    → 检查路径是否正确"
            )
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
                        "    → 在 lab.toml 的 [package] 下设置 memory_bench = true"
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
                f"  [agent.memory_chat_profile]\n"
                f"    文件不存在: {chat_profile_path}\n"
                "    → 检查路径是否正确"
            )

    if errors:
        logger.error("❌ 配置校验失败，请修复以下问题后重启：\n\n{}", "\n\n".join(errors))
        sys.exit(1)

    logger.info("✅ 配置校验通过")


@logger.catch
def run(lab_settings: XnneHangLabSettings, args: argparse.Namespace):
    """初始化日志与配置后启动 WebSocket 服务。

    Args:
        lab_settings: 已加载并校验结构的实验室配置对象。
        args: 命令行参数解析结果。

    Returns:
        None.
    """
    from lab.logger.logger_group import init_logger
    from lab.server import WebSocketServer

    init_logger()
    validate_config(lab_settings)
    logger.info(f"XnneHangLab, version v{get_version()}")

    server_config = lab_settings.server
    if args.port is not None:
        server_config.port = args.port

    # Initialize and run the WebSocket server
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

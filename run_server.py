from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import tomli
import uvicorn
from loguru import logger

from src.lab.config_manager import XnneHangLabSettings, load_settings_file
from src.lab.server import WebSocketServer

os.environ["HF_HOME"] = str(Path(__file__).parent / "models")
os.environ["MODELSCOPE_CACHE"] = str(Path(__file__).parent / "models")


def get_version() -> str:
    with Path("pyproject.toml").open("rb") as f:
        pyproject = tomli.load(f)
    return pyproject["project"]["version"]


def init_logger(console_log_level: str = "INFO") -> None:
    logger.remove()

    logger.add(
        sys.stderr,
        level="TRACE",  # 让 filter 来决定哪些放行
        filter={
            "": "WARNING",                  # 其他库默认只看 WARNING+
            "lab": "INFO",                  # 你的项目默认 INFO+
            "lab.mcp.tool_registry": "DEBUG"  # 这个模块单独 DEBUG
        },
        enqueue=True,
    )

    # File output
    logger.add(
        "logs/debug_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message} | {extra}",
        backtrace=True,
        diagnose=True,
    )


def parse_args(lab_settings: XnneHangLabSettings):
    parser = argparse.ArgumentParser(description="XnneHangLab Server")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--port", type=int, default=lab_settings.server.port, help="Server port")
    return parser.parse_args()


@logger.catch
def run(lab_settings: XnneHangLabSettings, args: argparse.Namespace):
    init_logger()
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
    )


if __name__ == "__main__":
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    args = parse_args(lab_settings)

    run(lab_settings=lab_settings, args=args)

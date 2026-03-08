from __future__ import annotations

import argparse
import os
from pathlib import Path

import tomli
import uvicorn
from loguru import logger

from lab.config_manager import XnneHangLabSettings, load_settings_file

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


@logger.catch
def run(lab_settings: XnneHangLabSettings, args: argparse.Namespace):
    from lab.logger.logger_group import init_logger
    from lab.server import WebSocketServer

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
        ws="websockets-sansio",
    )


if __name__ == "__main__":
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    args = parse_args(lab_settings)

    run(lab_settings=lab_settings, args=args)

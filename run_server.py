from __future__ import annotations

import argparse
import atexit
import gc
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import tomli
import torch
import uvicorn
from fastapi import FastAPI
from loguru import logger
from vits import utils
from vits.config import config
from vits.infer import get_net_g, latest_version
from vits.state_manager import tts_state_manager

from src.lab.api.core_logic import load_model
from src.lab.config_manager.vtuber import Config, read_yaml, validate_config

# from upgrade import sync_user_config, select_language
from src.lab.server import WebSocketServer

os.environ["HF_HOME"] = str(Path(__file__).parent / "models")
os.environ["MODELSCOPE_CACHE"] = str(Path(__file__).parent / "models")


def get_version() -> str:
    with open("pyproject.toml", "rb") as f:
        pyproject = tomli.load(f)
    return pyproject["project"]["version"]


def init_logger(console_log_level: str = "INFO") -> None:
    logger.remove()
    # Console output
    logger.add(
        sys.stderr,
        level=console_log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | {message}",
        colorize=True,
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


def parse_args():
    parser = argparse.ArgumentParser(description="Open-LLM-VTuber Server")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--hf_mirror", action="store_true", help="Use Hugging Face mirror")
    return parser.parse_args()


@logger.catch
def run(console_log_level: str):
    init_logger(console_log_level)
    logger.info(f"Open-LLM-VTuber, version v{get_version()}")

    # atexit.register(WebSocketServer.clean_cache)

    # Load configurations from yaml file
    config: Config = validate_config(read_yaml("config/vtuber.yaml"))
    server_config = config.system_config

    # Initialize and run the WebSocket server
    server = WebSocketServer(config=config)

    uvicorn.run(
        app=server.app,
        host=server_config.host,
        port=server_config.port,
        log_level=console_log_level.lower(),
    )


if __name__ == "__main__":
    args = parse_args()
    console_log_level = "DEBUG" if args.verbose else "INFO"
    # if args.verbose:
    #     logger.info("Running in verbose mode")
    # else:
    #     logger.info(
    #         "Running in standard mode. For detailed debug logs, use: uv run run_server.py --verbose"
    #     )
    if args.hf_mirror:
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    run(console_log_level=console_log_level)

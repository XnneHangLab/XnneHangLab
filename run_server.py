from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from src.lab.server import WebSocketServer

os.environ["HF_HOME"] = str(Path(__file__).parent / "models")
os.environ["MODELSCOPE_CACHE"] = str(Path(__file__).parent / "models")


def parse_args():
    parser = argparse.ArgumentParser(description="Open-LLM-VTuber Server")
    parser.add_argument("--hf_mirror", action="store_true", help="Use Hugging Face mirror")
    return parser.parse_args()


def run():
    # Load configurations from yaml file
    # Initialize and run the WebSocket server
    server = WebSocketServer()
    uvicorn.run(
        app=server.app,
        host="localhost",
        port=12393,
    )


if __name__ == "__main__":
    args = parse_args()
    run()

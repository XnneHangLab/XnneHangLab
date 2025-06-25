from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, File, Response, UploadFile, WebSocket
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from lab._dataclass import RunnerSettings
from lab.api.core_logic import rec_audio
from lab.api.routes.audio import generate_tts_direct
from lab.utils.config import load_settings_file
from lab.utils.Timedhelper import get_time_tag_with_millis

from .service_context import ServiceContext
from .websocket_handler import WebSocketHandler


def init_client_ws_route(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create and return API routes for handling the `/client-ws` WebSocket connections.

    Args:
        default_context_cache: Default service context cache for new sessions.

    Returns:
        APIRouter: Configured router with WebSocket endpoint.
    """

    router = APIRouter()
    ws_handler = WebSocketHandler(default_context_cache)

    @router.websocket("/client-ws")
    async def websocket_endpoint(websocket: WebSocket):  # type: ignore[no-untyped-def]
        """WebSocket endpoint for client connections"""
        await websocket.accept()
        client_uid = str(uuid4())

        try:
            await ws_handler.handle_new_connection(websocket, client_uid)
            await ws_handler.handle_websocket_communication(websocket, client_uid)
        except WebSocketDisconnect:
            await ws_handler.handle_disconnect(client_uid)
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {e}")
            await ws_handler.handle_disconnect(client_uid)
            raise

    return router


def init_webtool_routes(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create and return API routes for handling web tool interactions.

    Args:
        default_context_cache: Default service context cache for new sessions.

    Returns:
        APIRouter: Configured router with WebSocket endpoint.
    """

    router = APIRouter()
    file_default = File(...)

    @router.get("/web-tool")
    async def web_tool_redirect():  # type: ignore[no-untyped-def]
        """Redirect /web-tool to /web_tool/index.html"""
        return Response(status_code=302, headers={"Location": "/web-tool/index.html"})

    @router.get("/web_tool")
    async def web_tool_redirect_alt():  # type: ignore[no-untyped-def]
        """Redirect /web_tool to /web_tool/index.html"""
        return Response(status_code=302, headers={"Location": "/web-tool/index.html"})

    @router.post("/asr")
    async def transcribe_audio(file: UploadFile = file_default):  # type: ignore[no-untyped-def]
        """
        Convert uploaded audio file to SRT format.
        Returns processing information and the path to the generated SRT file.
        """
        settings = load_settings_file("global.toml", RunnerSettings)
        # 定义临时文件路径，如果文件名不存在则使用默认值
        temp_audio_path = Path(settings.cache_dir) / (
            file.filename if file.filename else f"temp_audio_{get_time_tag_with_millis()}.wav"
        )
        # 确保缓存目录存在
        temp_audio_path.parent.mkdir(parents=True, exist_ok=True)
        # 以二进制写入模式打开文件，并将上传的文件内容写入
        with temp_audio_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        # TODO 检查文件完整性
        # 处理音频文件
        result = rec_audio(input_path=temp_audio_path)
        # 清理临时文件
        temp_audio_path.unlink(missing_ok=True)
        return result

    @router.websocket("/tts-ws")
    async def tts_endpoint(websocket: WebSocket):
        """WebSocket endpoint for TTS generation"""
        await websocket.accept()
        logger.info("TTS WebSocket connection established")

        try:
            while True:
                data = await websocket.receive_json()
                text = data.get("text")
                if not text:
                    continue

                logger.info(f"Received text for TTS: {text}")

                # Split text into sentences
                sentences = [s.strip() for s in text.split(".") if s.strip()]

                try:
                    # Generate and send audio for each sentence
                    for sentence in sentences:
                        sentence = sentence + "."  # Add back the period
                        file_name = Path(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid4())[:8]}")
                        audio_path = await generate_tts_direct(text=sentence, file_path=file_name)
                        logger.info(f"Generated audio for sentence: {sentence} at: {audio_path}")

                        await websocket.send_json(
                            {
                                "status": "partial",
                                "audioPath": audio_path,
                                "text": sentence,
                            }
                        )

                    # Send completion signal
                    await websocket.send_json({"status": "complete"})

                except Exception as e:
                    logger.error(f"Error generating TTS: {e}")
                    await websocket.send_json({"status": "error", "message": str(e)})

        except WebSocketDisconnect:
            logger.info("TTS WebSocket client disconnected")
        except Exception as e:
            logger.error(f"Error in TTS WebSocket connection: {e}")
            await websocket.close()

    return router

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import numpy as np
from loguru import logger

from lab.conversations.chat_history_manager import store_message
from lab.conversations.conversation_utils import EMOJI_LIST
from lab.conversations.single_conversation import process_single_conversation

if TYPE_CHECKING:
    from fastapi import WebSocket

    from lab.service_context import ServiceContext


async def handle_conversation_trigger(
    msg_type: str,
    data: dict[Any, Any],
    client_uid: str,
    context: ServiceContext,
    websocket: WebSocket,
    received_data_buffers: dict[str, np.ndarray[Any, Any]],
    current_conversation_tasks: dict[str, asyncio.Task | None],  # type: ignore
) -> None:
    """Handle triggers that start a conversation"""
    if msg_type == "ai-speak-signal":
        user_input = ""
        await websocket.send_text(
            json.dumps(
                {
                    "type": "full-text",
                    "text": "AI wants to speak something...",
                }
            )
        )
    elif msg_type == "text-input":
        user_input = data.get("text", "")
    else:  # mic-audio-end
        user_input = received_data_buffers[client_uid]
        received_data_buffers[client_uid] = np.array([])

    images = data.get("images")
    # logger.info(f"Received images: {images}")
    # [{'source': 'upload', 'data': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA4QAAAKeCAYAAADAeD/Mw...', 'mime': 'image/png'}]
    # [{'source': 'upload', 'data': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA4QAAAKeCAYAAADAeD/Mw...', 'mime': 'image/jpeg'}]
    session_emoji = np.random.choice(EMOJI_LIST)

    logger.debug(f"Starting new single conversation for {client_uid}")
    current_conversation_tasks[client_uid] = asyncio.create_task(
        process_single_conversation(
            context=context,
            websocket_send=websocket.send_text,
            client_uid=client_uid,
            user_input=user_input,
            images=images,
            session_emoji=session_emoji,
        )
    )


async def handle_individual_interrupt(
    client_uid: str,
    current_conversation_tasks: dict[str, asyncio.Task | None],  # type: ignore
    context: ServiceContext,
    heard_response: str,
):
    if client_uid in current_conversation_tasks:
        task = current_conversation_tasks[client_uid]  # type: ignore
        if task and not task.done():
            task.cancel()
            logger.debug("🛑 Conversation task was successfully interrupted")

        if context.history_uid:
            if context.character_config is None:
                logger.error("character_config is None, cannot store message")
                raise ValueError("character_config cannot be None")
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="assistant",
                content=heard_response,
                name=context.character_config.character_name,
                avatar=context.character_config.avatar,
            )
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="system",
                content="[Interrupted by user]",
            )


async def handle_group_interrupt(
    group_id: str,
) -> None:
    """Handles interruption for a group conversation"""
    logger.debug(f"handle_group_interrupt called for group {group_id}")

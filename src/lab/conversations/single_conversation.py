from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Union

import numpy as np
from loguru import logger

from lab.agent.input_types import BatchInput
from lab.agent.output_types import Actions, DisplayText, SentenceOutput
from lab.api.openai import get_openai_response

from ..chat_history_manager import store_message
from ..service_context import ServiceContext
from .conversation_utils import (
    EMOJI_LIST,
    cleanup_conversation,
    create_batch_input,
    finalize_conversation_turn,
    process_agent_output,
    process_user_input,
    send_conversation_start_signals,
)
from .tts_manager import TTSTaskManager
from .types import WebSocketSend


async def process_single_conversation(
    context: ServiceContext,
    websocket_send: WebSocketSend,
    client_uid: str,
    user_input: Union[str, np.ndarray],
    images: Optional[List[Dict[str, Any]]] = None,
    session_emoji: str = np.random.choice(EMOJI_LIST),
) -> str:
    """Process a single-user conversation turn

    Args:
        context: Service context containing all configurations and engines
        websocket_send: WebSocket send function
        client_uid: Client unique identifier
        user_input: Text or audio input from user
        images: Optional list of image data
        session_emoji: Emoji identifier for the conversation

    Returns:
        str: Complete response text
    """
    # Create TTSTaskManager for this conversation
    tts_manager = TTSTaskManager()

    try:
        # Send initial signals
        await send_conversation_start_signals(websocket_send)
        logger.info(f"New Conversation Chain {session_emoji} started!")

        # Process user input
        if isinstance(user_input, np.ndarray):
            input_text = await process_user_input(user_input, websocket_send)
        else:
            input_text = user_input
            logger.info(f"User input: {input_text}")
            logger.info(f"User input type: {type(input_text)}")

        # Create batch input
        batch_input = create_batch_input(
            input_text=input_text,
            images=images,
            from_name=context.character_config.human_name,
        )

        # Store user message
        if context.history_uid:
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="human",
                content=input_text,
                name=context.character_config.human_name,
            )
        logger.info(f"User input: {input_text}")
        if images:
            logger.info(f"With {len(images)} images")

        # Process agent response
        full_response = await process_agent_response(
            context=context,
            batch_input=batch_input,
            websocket_send=websocket_send,
            tts_manager=tts_manager,
        )

        # Wait for any pending TTS tasks
        if tts_manager.task_list:
            await asyncio.gather(*tts_manager.task_list)
            await websocket_send(json.dumps({"type": "backend-synth-complete"}))

        await finalize_conversation_turn(
            tts_manager=tts_manager,
            websocket_send=websocket_send,
            client_uid=client_uid,
        )

        if context.history_uid and full_response:
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="ai",
                content=full_response,
                name=context.character_config.character_name,
                avatar=context.character_config.avatar,
            )
            logger.info(f"AI response: {full_response}")

        return full_response

    except asyncio.CancelledError:
        logger.info(f"🤡👍 Conversation {session_emoji} cancelled because interrupted.")
        raise
    except Exception as e:
        logger.error(f"Error in conversation chain: {e}")
        await websocket_send(json.dumps({"type": "error", "message": f"Conversation error: {str(e)}"}))
        raise
    finally:
        cleanup_conversation(tts_manager, session_emoji)


async def chat(input_text: str):
    text = get_openai_response(prompt=input_text)
    actions = Actions()
    display = DisplayText(text)
    logger.info(display)
    yield SentenceOutput(display, text, actions)


async def process_agent_response(
    context: ServiceContext,
    batch_input: BatchInput,
    websocket_send: WebSocketSend,
    tts_manager: TTSTaskManager,
) -> str:
    """Process agent response and generate output

    Args:
        context: Service context containing all configurations and engines
        batch_input: Input data for the agent
        websocket_send: WebSocket send function
        tts_manager: TTSTaskManager for the conversation

    Returns:
        str: The complete response text
    """
    full_response = ""
    try:
        # agent 记忆和输入是分开的。
        if not batch_input:
            raise ValueError("batch_input cannot be empty")
        else:
            agent_output = chat(batch_input.texts[-1].content)
        # else:
        #     raise TypeError("batch_input must be str")
        async for output in agent_output:
            logger.info("process agent output")
            response_part = await process_agent_output(
                output=output,
                character_config=context.character_config,
                live2d_model=context.live2d_model,
                # tts_engine=context.tts_engine,
                websocket_send=websocket_send,
                tts_manager=tts_manager,
                # translate_engine=context.translate_engine,
            )
            full_response += response_part

    except Exception as e:
        logger.error(f"Error processing agent response: {e}")
        raise
    logger.info("return full_response")
    return full_response

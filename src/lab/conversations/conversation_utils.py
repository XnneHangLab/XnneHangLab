from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import soundfile as sf
from loguru import logger

from lab.agent.input_types import BatchInput, ImageData, ImageSource, TextData, TextSource
from lab.api.clients import ASRClient, ASRRequest, DeepLXClient, DeepLXRequest
from lab.config_manager import AgentSettings, load_settings_file
from lab.message_handler import message_handler

if TYPE_CHECKING:
    from lab.agent.output_types import SentenceOutput
    from lab.conversations.tts_manager import TTSTaskManager
    from lab.conversations.types import BroadcastContext, WebSocketSend
    from lab.live2d_model import Live2dModel


# Convert class methods to standalone functions
def create_batch_input(
    input_text: str,
    images: list[dict[str, Any]] | None,
    from_name: str,
) -> BatchInput:
    """Create batch input for agent processing"""
    return BatchInput(
        texts=[TextData(source=TextSource.INPUT, content=input_text, from_name=from_name)],
        images=[
            ImageData(
                source=ImageSource(img["source"]),
                data=img["data"],
                mime_type=img["mime_type"],
            )
            for img in (images or [])
        ]
        if images
        else None,
    )


async def process_agent_output(
    output: SentenceOutput,  # 我们不使用 human ai ，所以仅有 SentenceOutput, voice 通过 tts 生成
    character_config: Any,
    live2d_model: Live2dModel,
    # tts_engine: TTSInterface,
    websocket_send: WebSocketSend,
    tts_manager: TTSTaskManager,
    # translate_engine: Optional[Any] = None,
) -> str:
    """Process agent output with character information and optional translation"""
    output.display_text.name = character_config.character_name
    output.display_text.avatar = character_config.avatar

    full_response = ""
    try:
        # if isinstance(output, SentenceOutput):
        logger.info("SentenceOutput Detect")
        full_response = await handle_sentence_output(
            output,
            live2d_model,
            # tts_engine,
            websocket_send,
            tts_manager,
            # translate_engine,
        )
    except Exception as e:
        logger.error(f"Error processing agent output: {e}")
        await websocket_send(json.dumps({"type": "error", "message": f"Error processing response: {str(e)}"}))

    return full_response


async def handle_sentence_output(
    output: SentenceOutput,
    live2d_model: Live2dModel,
    # tts_engine: TTSInterface,
    websocket_send: WebSocketSend,
    tts_manager: TTSTaskManager,
    # translate_engine: Optional[Any] = None,
) -> str:
    """Handle sentence output type with optional translation support"""
    full_response = ""
    agent_settings = load_settings_file("agent.toml", AgentSettings)
    async for display_text, tts_text, actions in output:
        logger.info(f"🏃 Processing output: '''{tts_text}'''...")

        # if translate_engine:
        #     if len(re.sub(r'[\s.,!?，。！？\'"』」）】\s]+', "", tts_text)):
        #         tts_text = translate_engine.translate(tts_text)
        #     logger.info(f"🏃 Text after translation: '''{tts_text}'''...")
        # else:
        # logger.info("🚫 No translation engine available. Skipping translation.")
        if agent_settings.speaker_lang != "ZH":
            logger.info(f"🏃 Translating text to {agent_settings.speaker_lang}...")
            deeplx_client = DeepLXClient()
            response = await deeplx_client.asyncpost(
                DeepLXRequest(text=tts_text, source_language="ZH", target_language=agent_settings.speaker_lang)
            )
            tts_text = response["target_text"] if response else tts_text
            logger.info(f"🏃 Text after translation: '''{tts_text}'''...")

        full_response += display_text.text
        await tts_manager.speak(
            tts_text=tts_text,
            display_text=display_text,
            actions=actions,
            live2d_model=live2d_model,
            # tts_engine=tts_engine,
            websocket_send=websocket_send,
        )
    return full_response


async def send_conversation_start_signals(websocket_send: WebSocketSend) -> None:
    """Send initial conversation signals"""
    await websocket_send(
        json.dumps(
            {
                "type": "control",
                "text": "conversation-chain-start",
            }
        )
    )
    await websocket_send(json.dumps({"type": "full-text", "text": "Thinking..."}))


async def process_user_input(
    user_input: str | np.ndarray[Any, Any],  #  text, 或者 mico
    # asr_engine: Any,  # 假设 asr_engine 存在，修正注释中的类型提示
    websocket_send: WebSocketSend,
) -> str:
    """Process user input, converting audio to text if needed"""
    if isinstance(user_input, np.ndarray):
        logger.info("Transcribing audio input...")
        # 确保 cache 目录存在
        cache_dir = Path("cache")
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 生成唯一的文件名
        audio_file_path = cache_dir / "temp_audio.wav"
        unique_suffix = 1
        while audio_file_path.exists():
            audio_file_path = cache_dir / f"temp_audio_{unique_suffix}.wav"
            unique_suffix += 1

        try:
            # 将音频数据写入文件
            sf.write(audio_file_path, user_input, samplerate=16000)  # 假设采样率为 16000 Hz # type: ignore
            # 使用文件路径调用异步转录方法
            asr_client = ASRClient()
            response = await asr_client.asyncpost(ASRRequest(file_path=audio_file_path))
            if response is None:
                raise ValueError("ASR response is None")
            await websocket_send(json.dumps({"type": "user-input-transcription", "text": response["text"]}))
        finally:
            # 删除临时音频文件
            if audio_file_path.exists():
                audio_file_path.unlink()

        return response["text"]  # TODO, 规范化我们的 routes 输出，以 TypedDict 约束
    else:
        logger.info(f"User input: {user_input}")
        # await websocket_send(json.dumps({"type": "user-input-text", "text": user_input}))
        return user_input


async def finalize_conversation_turn(
    tts_manager: TTSTaskManager,
    websocket_send: WebSocketSend,
    client_uid: str,
    broadcast_ctx: BroadcastContext | None = None,
) -> None:
    """Finalize a conversation turn"""
    if tts_manager.task_list:  # type: ignore
        await asyncio.gather(*tts_manager.task_list)  # type: ignore
        await websocket_send(json.dumps({"type": "backend-synth-complete"}))

        response = await message_handler.wait_for_response(client_uid, "frontend-playback-complete")  # type: ignore

        if not response:
            logger.warning(f"No playback completion response from {client_uid}")
            return

    await websocket_send(json.dumps({"type": "force-new-message"}))

    if broadcast_ctx and broadcast_ctx.broadcast_func:  # type: ignore
        await broadcast_ctx.broadcast_func(  # type: ignore
            broadcast_ctx.group_members,  # type: ignore
            {"type": "force-new-message"},
            broadcast_ctx.current_client_uid,
        )

    await send_conversation_end_signal(websocket_send, broadcast_ctx)


async def send_conversation_end_signal(
    websocket_send: WebSocketSend,
    broadcast_ctx: BroadcastContext | None,
    session_emoji: str = "😊",
) -> None:
    """Send conversation chain end signal"""
    chain_end_msg = {
        "type": "control",
        "text": "conversation-chain-end",
    }

    await websocket_send(json.dumps(chain_end_msg))

    if broadcast_ctx and broadcast_ctx.broadcast_func and broadcast_ctx.group_members:  # type: ignore
        await broadcast_ctx.broadcast_func(  # type: ignore
            broadcast_ctx.group_members,
            chain_end_msg,
        )

    logger.info(f"😎👍✅ Conversation Chain {session_emoji} completed!")


def cleanup_conversation(tts_manager: TTSTaskManager, session_emoji: str) -> None:
    """Clean up conversation resources"""
    tts_manager.clear()
    logger.debug(f"🧹 Clearing up conversation {session_emoji}.")


EMOJI_LIST = [
    "🐶",
    "🐱",
    "🐭",
    "🐹",
    "🐰",
    "🦊",
    "🐻",
    "🐼",
    "🐨",
    "🐯",
    "🦁",
    "🐮",
    "🐷",
    "🐸",
    "🐵",
    "🐔",
    "🐧",
    "🐦",
    "🐤",
    "🐣",
    "🐥",
    "🦆",
    "🦅",
    "🦉",
    "🦇",
    "🐺",
    "🐗",
    "🐴",
    "🦄",
    "🐝",
    "🌵",
    "🎄",
    "🌲",
    "🌳",
    "🌴",
    "🌱",
    "🌿",
    "☘️",
    "🍀",
    "🍂",
    "🍁",
    "🍄",
    "🌾",
    "💐",
    "🌹",
    "🌸",
    "🌛",
    "🌍",
    "⭐️",
    "🔥",
    "🌈",
    "🌩",
    "⛄️",
    "🎃",
    "🎄",
    "🎉",
    "🎏",
    "🎗",
    "🀄️",
    "🎭",
    "🎨",
    "🧵",
    "🪡",
    "🧶",
    "🥽",
    "🥼",
    "🦺",
    "👔",
    "👕",
    "👜",
    "👑",
]

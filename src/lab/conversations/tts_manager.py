from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from lab.agent.output_types import Actions, DisplayText
from lab.api.routes.vits import generate_tts_direct
from lab.conversations.types import WebSocketSend
from lab.live2d_model import Live2dModel
from lab.utils.stream_audio import prepare_audio_payload


class TTSTaskManager:
    """Manages TTS tasks and ensures ordered delivery to frontend while allowing parallel TTS generation"""

    def __init__(self) -> None:
        self.task_list: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        # Queue to store ordered payloads
        self._payload_queue: asyncio.Queue[Dict] = asyncio.Queue()
        # Task to handle sending payloads in order
        self._sender_task: Optional[asyncio.Task] = None
        # Counter for maintaining order
        self._sequence_counter = 0
        self._next_sequence_to_send = 0

    async def speak(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Optional[Actions],
        live2d_model: Live2dModel,
        websocket_send: WebSocketSend,
    ) -> None:
        """
        Queue a TTS task while maintaining order of delivery.

        Args:
            tts_text: Text to synthesize
            display_text: Text to display in UI
            actions: Live2D model actions
            live2d_model: Live2D model instance
            tts_engine: TTS engine instance
            websocket_send: WebSocket send function
        """
        if len(re.sub(r'[\s.,!?，。！？\'"』」）】\s]+', "", tts_text)) == 0:
            logger.info("Empty TTS text, sending silent display payload")
            # Get current sequence number for silent payload
            current_sequence = self._sequence_counter
            self._sequence_counter += 1

            # Start sender task if not running
            if not self._sender_task or self._sender_task.done():
                self._sender_task = asyncio.create_task(self._process_payload_queue(websocket_send))

            await self._send_silent_payload(display_text, actions, current_sequence)
            return

        logger.info(f"🏃Queuing TTS task for: '''{tts_text}''' (by {display_text.name})")

        # Get current sequence number
        current_sequence = self._sequence_counter
        self._sequence_counter += 1

        # Start sender task if not running
        if not self._sender_task or self._sender_task.done():
            self._sender_task = asyncio.create_task(self._process_payload_queue(websocket_send))

        # Create and queue the TTS task
        task = asyncio.create_task(
            self._process_tts(
                tts_text=tts_text,
                display_text=display_text,
                actions=actions,
                live2d_model=live2d_model,
                # tts_engine=tts_engine,
                sequence_number=current_sequence,
            )
        )
        self.task_list.append(task)

    async def _process_payload_queue(self, websocket_send: WebSocketSend) -> None:
        """
        Process and send payloads in correct order.
        Runs continuously until all payloads are processed.
        """
        buffered_payloads: Dict[int, Dict] = {}
        logger.info("Starting TTS payload sender task...")

        while True:
            # try:
            # Get payload from queue
            payload, sequence_number = await self._payload_queue.get()
            buffered_payloads[sequence_number] = payload

            # Send payloads in order
            while self._next_sequence_to_send in buffered_payloads:
                next_payload = buffered_payloads.pop(self._next_sequence_to_send)
                await websocket_send(json.dumps(next_payload))
                self._next_sequence_to_send += 1

            self._payload_queue.task_done()

    async def _send_silent_payload(
        self,
        display_text: DisplayText,
        actions: Optional[Actions],
        sequence_number: int,
    ) -> None:
        """Queue a silent audio payload"""
        audio_payload = prepare_audio_payload(
            audio_path=None,
            display_text=display_text,
            actions=actions,
        )
        await self._payload_queue.put((audio_payload, sequence_number))

    async def _process_tts(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Optional[Actions],
        live2d_model: Live2dModel,
        # tts_engine: TTSInterface,
        sequence_number: int,
    ) -> None:
        """Process TTS generation and queue the result for ordered delivery"""
        audio_file_path = None
        # try:
        audio_file_path = await self._generate_audio(tts_text)
        if not audio_file_path:
            raise ValueError("Audio file path is None")
        payload = prepare_audio_payload(
            audio_path=str(audio_file_path),
            display_text=display_text,
            actions=actions,
        )
        # Queue the payload with its sequence number
        await self._payload_queue.put((payload, sequence_number))

        # except Exception as e:
        #     logger.error(f"Error preparing audio payload: {e}")
        #     # Queue silent payload for error case
        #     payload = prepare_audio_payload(
        #         audio_path=None,
        #         display_text=display_text,
        #         actions=actions,
        #     )
        #     await self._payload_queue.put((payload, sequence_number))

        # finally:
        # if isinstance(audio_file_path,Path):
        #     audio_file_path.unlink()
        #     logger.debug("Audio cache file cleaned.")
        # pass

    async def _generate_audio(self, text: str) -> Path | None:
        """Generate audio file from text"""
        try:
            logger.debug(f"🏃Generating audio for '''{text}'''...")
            cache_dir = Path("cache") / "tts"
            audio_path = await generate_tts_direct(
                text=text,
                file_path=cache_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}.opus",
            )
            if not audio_path.exists():
                logger.error("generate_tts_direct returned None")
            else:
                logger.info(f"Generated audio file at {audio_path}")
            return audio_path
        except Exception as e:
            logger.error(f"Error generating audio: {e}", exc_info=True)
            return None

    def clear(self) -> None:
        """Clear all pending tasks and reset state"""
        self.task_list.clear()
        if self._sender_task:
            self._sender_task.cancel()
        self._sequence_counter = 0
        self._next_sequence_to_send = 0
        # Create a new queue to clear any pending items
        logger.info("Clearing TTS payload queue...")
        self._payload_queue = asyncio.Queue()

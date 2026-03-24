from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.utils.stream_audio import AudioPayload, prepare_audio_payload

if TYPE_CHECKING:
    from lab.agent.output_types import Actions, DisplayText
    from lab.config_manager.vtuber import CharacterSettings
    from lab.conversations.types import WebSocketSend
    from lab.live2d_model import Live2dModel


_NON_SPOKEN_TTS_RE = re.compile(r'[\s.,!?，。！？\'"』」）】()\[\]{}…\-\n\r\t]+')
_TOOL_STATUS_DISPLAY_RE = re.compile(r"\[\s*🔧[^\]]*]")
_TOOL_STATUS_XML_RE = re.compile(r"<tool>.*?</tool>", re.DOTALL)


def _summarize_text(text: str | None, *, limit: int = 48) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def has_audible_tts_text(tts_text: str) -> bool:
    """Return True only when the text has something worth translating or speaking."""
    normalized = (tts_text or "").replace("*", "")
    normalized = _TOOL_STATUS_XML_RE.sub("", normalized)
    normalized = _TOOL_STATUS_DISPLAY_RE.sub("", normalized)
    return len(_NON_SPOKEN_TTS_RE.sub("", normalized)) > 0


def _resolve_ref_audio_and_text(
    character_config: CharacterSettings | None,
    emotion_keys: list[str] | None,
) -> tuple[str | None, str | None]:
    """Resolve ref_audio and optional ref_text from the current character TTS config."""

    if character_config is None:
        return None, None

    tts_cfg = character_config.tts_config
    if not tts_cfg.character_name:
        return None, None

    base = Path("models/gptsovits") / tts_cfg.character_name
    emotions = tts_cfg.emotions
    if not emotions:
        logger.error("No GPT-SoVITS emotions configured for character: {}", tts_cfg.character_name)
        return None, None

    candidates = [key for key in emotion_keys or [] if key]

    for key in candidates:
        emotion = emotions.get(key)
        if emotion is None or not emotion.path:
            continue
        candidate = base / emotion.path
        if candidate.is_file():
            return str(candidate), (emotion.ref_text or None)

    first_emotion = next(iter(emotions.values()), None)
    if first_emotion is not None and first_emotion.path:
        candidate = base / first_emotion.path
        if candidate.is_file():
            return str(candidate), (first_emotion.ref_text or None)

    return None, None


class TTSTaskManager:
    """Manages TTS tasks and ensures ordered delivery to frontend while allowing parallel TTS generation"""

    def __init__(self) -> None:
        self.task_list: list[asyncio.Task[None]] = []
        self._lock = asyncio.Lock()
        self._payload_queue: asyncio.Queue[tuple[AudioPayload, int]] = asyncio.Queue()
        self._sender_task: asyncio.Task[None] | None = None
        self._sequence_counter = 0
        self._next_sequence_to_send = 0

    def has_output(self) -> bool:
        """Return True when this turn queued any display or audio payload."""
        return self._sequence_counter > 0

    async def speak(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Actions | None,
        live2d_model: Live2dModel | None,
        websocket_send: WebSocketSend,
        character_config: CharacterSettings | None = None,
    ) -> None:
        """
        Queue a TTS task while maintaining order of delivery.

        Args:
            tts_text: Text to synthesize
            display_text: Text to display in UI
            actions: Live2D model actions
            live2d_model: Live2D model instance
            websocket_send: WebSocket send function
            character_config: Current runtime character configuration
        """
        if not has_audible_tts_text(tts_text):
            logger.debug("Empty TTS text, sending silent display payload")
            current_sequence = self._sequence_counter
            self._sequence_counter += 1

            if self._sender_task is None or self._sender_task.done():
                self._sender_task = asyncio.create_task(self._process_payload_queue(websocket_send))

            await self._send_silent_payload(display_text, actions, current_sequence)
            return

        current_sequence = self._sequence_counter
        self._sequence_counter += 1

        if self._sender_task is None or self._sender_task.done():
            self._sender_task = asyncio.create_task(self._process_payload_queue(websocket_send))

        task = asyncio.create_task(
            self._process_tts(
                tts_text=tts_text,
                display_text=display_text,
                actions=actions,
                live2d_model=live2d_model,
                character_config=character_config,
                sequence_number=current_sequence,
            )
        )
        self.task_list.append(task)

    async def _process_payload_queue(self, websocket_send: WebSocketSend) -> None:
        """Process and send payloads in correct order."""
        buffered_payloads: dict[int, AudioPayload] = {}
        logger.debug("Starting TTS payload sender task...")

        while True:
            payload, sequence_number = await self._payload_queue.get()
            sequence_number = int(sequence_number)
            buffered_payloads[sequence_number] = payload

            if sequence_number != self._next_sequence_to_send:
                logger.debug(
                    "[TTS_SEND] payload ready but waiting for earlier seq: ready_seq={} next_seq={} text={}",
                    sequence_number,
                    self._next_sequence_to_send,
                    _summarize_text(payload.get("display_text", {}).get("text")),  # type: ignore[arg-type]
                )

            while self._next_sequence_to_send in buffered_payloads:
                next_payload = buffered_payloads.pop(self._next_sequence_to_send)
                display_text = next_payload.get("display_text", {})
                logger.debug(
                    "[TTS_SEND] payload sent seq={} has_audio={} text={}",
                    self._next_sequence_to_send,
                    bool(next_payload.get("audio")),
                    _summarize_text(display_text.get("text")),  # type: ignore[arg-type]
                )
                await websocket_send(json.dumps(next_payload))
                self._next_sequence_to_send += 1

            self._payload_queue.task_done()

    async def _send_silent_payload(
        self,
        display_text: DisplayText,
        actions: Actions | None,
        sequence_number: int,
    ) -> None:
        """Queue a silent audio payload."""
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
        actions: Actions | None,
        live2d_model: Live2dModel | None,
        character_config: CharacterSettings | None,
        sequence_number: int,
    ) -> None:
        """Process TTS generation and queue the result for ordered delivery."""
        del live2d_model
        emotion_keys = actions.emotion_keys if actions is not None else None
        audio_file_path = await self._generate_audio(
            tts_text,
            character_config=character_config,
            emotion_keys=emotion_keys,
        )
        if not audio_file_path:
            raise ValueError("Audio file path is None")
        payload = prepare_audio_payload(
            audio_path=str(audio_file_path),
            display_text=display_text,
            actions=actions,
        )
        logger.debug(
            "[TTS_READY] audio ready seq={} text={}",
            sequence_number,
            _summarize_text(display_text.text),
        )
        await self._payload_queue.put((payload, sequence_number))

    async def _generate_audio(
        self,
        text: str,
        character_config: CharacterSettings | None = None,
        emotion_keys: list[str] | None = None,
    ) -> Path | None:
        """Generate audio file from text."""
        try:
            lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
            cache_dir = Path("cache") / "tts"
            cache_dir.mkdir(parents=True, exist_ok=True)
            if lab_settings.agent.speaker_model == "gpt_sovits":
                from lab.api.clients import GPTSoVITSClient, GPTSoVITSRequest

                gpt_sovits_client = GPTSoVITSClient()
                ref_audio_path, ref_text = _resolve_ref_audio_and_text(character_config, emotion_keys)
                response = await gpt_sovits_client.asyncpost(
                    GPTSoVITSRequest(
                        text=text,
                        audio_type="mp3",
                        ref_audio_path=ref_audio_path,
                        prompt_text=ref_text,
                        text_language=lab_settings.agent.speaker_lang,
                    )
                )
                if response is None:
                    logger.error(
                        "Failed to get a valid response from GPT-SoVITS client: {}",
                        gpt_sovits_client.last_error or "unknown error",
                    )
                    return None
            else:
                logger.error(f"Unsupported speaker model: {lab_settings.agent.speaker_model}")
                return None
            audio_path = (
                cache_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid4())[:8]}.{response['audio_type']}"
            )
            with audio_path.open("wb") as f:
                f.write(response["audio_byte"])
            return Path(audio_path)
        except Exception as e:
            logger.error(f"Error generating audio: {e}", exc_info=True)
            return None

    async def wait_until_all_payloads_sent(self) -> None:
        """Wait until all queued TTS work has been converted and sent to the frontend."""
        if self.task_list:
            await asyncio.gather(*self.task_list)
        if self._sender_task is not None:
            await self._payload_queue.join()

    def clear(self) -> None:
        """Clear all pending tasks and reset state."""
        self.task_list.clear()
        if self._sender_task:
            self._sender_task.cancel()
        self._sequence_counter = 0
        self._next_sequence_to_send = 0
        logger.debug("Clearing TTS payload queue...")
        self._payload_queue = asyncio.Queue()

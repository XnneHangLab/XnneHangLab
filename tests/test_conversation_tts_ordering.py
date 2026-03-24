from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import lab.conversations.conversation_utils as conversation_utils_module
import lab.conversations.tts_manager as tts_manager_module
from lab.agent.output_types import Actions, DisplayText
from lab.conversations.conversation_utils import finalize_conversation_turn
from lab.conversations.tts_manager import TTSTaskManager


def test_finalize_waits_for_all_audio_payloads_before_backend_complete(monkeypatch) -> None:
    sent_messages: list[dict[str, Any]] = []

    async def websocket_send(payload: str) -> None:
        sent_messages.append(json.loads(payload))

    async def fake_generate_audio(
        self: TTSTaskManager,
        text: str,
        character_config: object | None = None,
        emotion_keys: list[str] | None = None,
    ) -> Path:
        del self, character_config, emotion_keys
        await asyncio.sleep(0.05 if text == "first" else 0.0)
        return Path(f"{text}.wav")

    def fake_prepare_audio_payload(
        audio_path: str | None,
        display_text: DisplayText,
        actions: Actions | None = None,
        chunk_length_ms: int = 20,
        forwarded: bool = False,
    ) -> dict[str, object]:
        del audio_path, actions
        return {
            "type": "audio",
            "audio": display_text.text,
            "volumes": [1.0],
            "slice_length": chunk_length_ms,
            "display_text": display_text.to_dict(),
            "actions": None,
            "forwarded": forwarded,
        }

    async def fake_wait_for_response(client_uid: str, message_type: str) -> dict[str, str]:
        assert client_uid == "client-1"
        assert message_type == "frontend-playback-complete"
        return {"type": message_type}

    monkeypatch.setattr(TTSTaskManager, "_generate_audio", fake_generate_audio)
    monkeypatch.setattr(tts_manager_module, "prepare_audio_payload", fake_prepare_audio_payload)
    monkeypatch.setattr(conversation_utils_module.message_handler, "wait_for_response", fake_wait_for_response)

    async def run_test() -> None:
        manager = TTSTaskManager()
        try:
            await manager.speak("first", DisplayText("First sentence."), Actions(), None, websocket_send)
            await manager.speak("second", DisplayText("Second sentence."), Actions(), None, websocket_send)
            await finalize_conversation_turn(manager, websocket_send, "client-1")
        finally:
            manager.clear()

    asyncio.run(run_test())

    assert [message["type"] for message in sent_messages] == [
        "audio",
        "audio",
        "backend-synth-complete",
        "force-new-message",
        "control",
    ]
    assert sent_messages[0]["display_text"]["text"] == "First sentence."
    assert sent_messages[1]["display_text"]["text"] == "Second sentence."
    assert sent_messages[2]["type"] == "backend-synth-complete"

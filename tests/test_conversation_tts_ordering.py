from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import lab.api.clients.qwen_tts_client as qwen_tts_client_module
import lab.conversations.conversation_utils as conversation_utils_module
import lab.conversations.tts_manager as tts_manager_module
from lab.agent.output_types import Actions, DisplayText
from lab.conversations.conversation_utils import finalize_conversation_turn
from lab.conversations.tts_manager import TTSTaskManager

if TYPE_CHECKING:
    import pytest


def test_finalize_waits_for_all_audio_payloads_before_backend_complete(monkeypatch: pytest.MonkeyPatch) -> None:
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
        turn_id: str | None = None,
        tts_error: bool = False,
    ) -> dict[str, object]:
        del audio_path, actions, turn_id
        return {
            "type": "audio",
            "audio": display_text.text,
            "volumes": [1.0],
            "slice_length": chunk_length_ms,
            "display_text": display_text.to_dict(),
            "actions": None,
            "forwarded": forwarded,
            "tts_error": tts_error,
        }

    async def fake_wait_for_response(
        client_uid: str,
        message_type: str,
        timeout: float | None = None,
        response_filter: object | None = None,
    ) -> dict[str, str]:
        assert timeout is None
        del response_filter
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


def test_clear_cancels_pending_tts_before_later_sentences_start(monkeypatch: pytest.MonkeyPatch) -> None:
    started_texts: list[str] = []
    first_started = asyncio.Event()

    async def websocket_send(payload: str) -> None:
        del payload

    async def fake_generate_audio(
        self: TTSTaskManager,
        text: str,
        character_config: object | None = None,
        emotion_keys: list[str] | None = None,
    ) -> Path:
        del self, character_config, emotion_keys
        started_texts.append(text)
        if text == "first":
            first_started.set()
            await asyncio.sleep(0.2)
        return Path(f"{text}.wav")

    monkeypatch.setattr(TTSTaskManager, "_generate_audio", fake_generate_audio)

    async def run_test() -> None:
        manager = TTSTaskManager()
        try:
            await manager.speak("first", DisplayText("First sentence."), Actions(), None, websocket_send)
            await manager.speak("second", DisplayText("Second sentence."), Actions(), None, websocket_send)
            await first_started.wait()
            await asyncio.sleep(0)
            manager.clear()
            await asyncio.sleep(0)
        finally:
            manager.clear()

    asyncio.run(run_test())

    assert started_texts == ["first"]


def test_finalize_continues_when_frontend_playback_ack_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_messages: list[dict[str, Any]] = []

    async def websocket_send(payload: str) -> None:
        sent_messages.append(json.loads(payload))

    async def fake_wait_for_response(
        client_uid: str,
        message_type: str,
        timeout: float | None = None,
        response_filter: object | None = None,
    ) -> None:
        del client_uid, message_type, timeout, response_filter
        return None

    monkeypatch.setattr(conversation_utils_module.message_handler, "wait_for_response", fake_wait_for_response)

    async def run_test() -> None:
        manager = TTSTaskManager()
        try:
            await manager.speak("...", DisplayText("[tool]"), Actions(), None, websocket_send)
            await finalize_conversation_turn(manager, websocket_send, "client-1", turn_id="turn-1")
        finally:
            manager.clear()

    asyncio.run(run_test())

    assert [message["type"] for message in sent_messages] == [
        "audio",
        "backend-synth-complete",
        "force-new-message",
        "control",
    ]


def test_tts_timeout_degrades_to_silent_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_messages: list[dict[str, Any]] = []

    async def websocket_send(payload: str) -> None:
        sent_messages.append(json.loads(payload))

    class _FakeTTSSettings:
        provider = "qwen_tts"

    class _FakeAgentSettings:
        tts = _FakeTTSSettings()
        speaker_lang = "zh"

    class _FakeSettings:
        agent = _FakeAgentSettings()

    async def fake_qwen_asyncpost(self: object, request: object) -> object:
        del self, request
        await asyncio.sleep(0.05)
        return {
            "audio_type": "wav",
            "audio_byte": b"unused",
        }

    def fake_prepare_audio_payload(
        audio_path: str | None,
        display_text: DisplayText,
        actions: Actions | None = None,
        chunk_length_ms: int = 20,
        forwarded: bool = False,
        turn_id: str | None = None,
        tts_error: bool = False,
    ) -> dict[str, object]:
        del actions
        return {
            "type": "audio",
            "audio": audio_path,
            "volumes": [0.0],
            "slice_length": chunk_length_ms,
            "display_text": display_text.to_dict(),
            "actions": None,
            "forwarded": forwarded,
            "turn_id": turn_id,
            "tts_error": tts_error,
        }

    def fake_load_settings_file(*args: object, **kwargs: object) -> _FakeSettings:
        del args, kwargs
        return _FakeSettings()

    def fake_require_ref_audio_and_text(*args: object, **kwargs: object) -> tuple[str, None]:
        del args, kwargs
        return ("ref.wav", None)

    monkeypatch.setattr(tts_manager_module, "load_settings_file", fake_load_settings_file)
    monkeypatch.setattr(tts_manager_module, "_require_ref_audio_and_text", fake_require_ref_audio_and_text)
    monkeypatch.setattr(tts_manager_module, "TTS_GENERATION_TIMEOUT_S", 0.01)
    monkeypatch.setattr(qwen_tts_client_module.QwenTTSClient, "asyncpost", fake_qwen_asyncpost)
    monkeypatch.setattr(tts_manager_module, "prepare_audio_payload", fake_prepare_audio_payload)

    async def run_test() -> None:
        manager = TTSTaskManager(turn_id="turn-timeout")
        try:
            await manager.speak("timed out", DisplayText("Sentence after timeout."), Actions(), None, websocket_send)
            await manager.wait_until_all_payloads_sent()
        finally:
            manager.clear()

    asyncio.run(run_test())

    assert sent_messages == [
        {
            "type": "audio",
            "audio": None,
            "volumes": [0.0],
            "slice_length": 20,
            "display_text": DisplayText("Sentence after timeout.").to_dict(),
            "actions": None,
            "forwarded": False,
            "turn_id": "turn-timeout",
            "tts_error": True,
        }
    ]

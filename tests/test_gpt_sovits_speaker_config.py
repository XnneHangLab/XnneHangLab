# pyright: reportPrivateUsage=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import lab.api.clients as api_clients_module
import lab.conversations.tts_manager as tts_manager_module
from lab.config_manager.vtuber import CharacterSettings, TTSConfig
from lab.conversations.tts_manager import TTSTaskManager


def test_generate_audio_rejects_missing_configured_ref_audio(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_load_settings_file(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            agent=SimpleNamespace(
                tts=SimpleNamespace(provider="gpt_sovits"),
                speaker_lang="ZH",
            )
        )

    monkeypatch.setattr(tts_manager_module, "load_settings_file", fake_load_settings_file)

    captured_requests: list[dict[str, Any]] = []

    class FakeGPTSoVITSClient:
        last_error: str | None = None

        async def asyncpost(self, request: Any) -> dict[str, object]:
            captured_requests.append(request.model_dump())
            return {
                "audio_type": "mp3",
                "audio_rate": 32000,
                "audio_byte": b"",
            }

    monkeypatch.setattr(api_clients_module, "GPTSoVITSClient", FakeGPTSoVITSClient)

    manager = TTSTaskManager()
    character = CharacterSettings(
        tts_config=TTSConfig(
            character_name="baoqiao",
            emotions={
                "default": {
                    "path": "emotions/missing.wav",
                    "ref_text": "missing ref",
                }
            },
        )
    )

    result = asyncio.run(manager._generate_audio("test", character_config=character))

    assert result is None
    assert captured_requests == []

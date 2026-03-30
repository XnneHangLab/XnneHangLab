# pyright: reportPrivateUsage=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

import lab.api.clients as api_clients_module
import lab.conversations.tts_manager as tts_manager_module
from lab.config_manager.vtuber import CharacterSettings, TTSConfig
from lab.conversations.tts_manager import TTSTaskManager


def test_generate_audio_uses_gsv_lite_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ref_audio: Path = tmp_path / "models" / "gptsovits" / "baoqiao" / "emotions" / "neutral.wav"
    ref_audio.parent.mkdir(parents=True)
    ref_audio.write_bytes(b"wav")
    speaker_audio: Path = tmp_path / "models" / "gptsovits" / "baoqiao" / "speaker" / "neutral_speaker.wav"
    speaker_audio.parent.mkdir(parents=True)
    speaker_audio.write_bytes(b"wav")
    monkeypatch.chdir(tmp_path)

    def fake_load_settings_file(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            agent=SimpleNamespace(
                tts=SimpleNamespace(provider="gsv_lite"),
                speaker_lang="ZH",
            )
        )

    monkeypatch.setattr(tts_manager_module, "load_settings_file", fake_load_settings_file)

    captured_requests: list[dict[str, Any]] = []

    class FakeGSVLiteClient:
        last_error: str | None = None

        async def asyncpost(self, request: Any) -> dict[str, object]:
            captured_requests.append(request.model_dump())
            return {
                "audio_type": "wav",
                "audio_rate": 32000,
                "audio_byte": b"RIFFfakewav",
            }

    monkeypatch.setattr(api_clients_module, "GSVLiteClient", FakeGSVLiteClient)

    manager = TTSTaskManager()
    character = CharacterSettings(
        tts_config=TTSConfig(
            character_name="baoqiao",
            emotions={
                "default": {
                    "path": "emotions/neutral.wav",
                    "ref_text": "neutral ref",
                    "speaker_audio_path": "speaker/neutral_speaker.wav",
                }
            },
        )
    )

    result = asyncio.run(manager._generate_audio("test", character_config=character))

    assert result is not None
    assert result.exists()
    assert result.suffix == ".wav"
    assert len(captured_requests) == 1
    assert captured_requests[0]["text"] == "test"
    assert Path(captured_requests[0]["ref_audio_path"]) == Path("models/gptsovits/baoqiao/emotions/neutral.wav")
    assert captured_requests[0]["ref_text"] == "neutral ref"
    assert Path(captured_requests[0]["speaker_audio_path"]) == Path(
        "models/gptsovits/baoqiao/speaker/neutral_speaker.wav"
    )

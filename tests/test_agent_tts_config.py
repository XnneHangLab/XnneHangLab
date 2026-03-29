from __future__ import annotations

from typing import TYPE_CHECKING

from lab.config_manager.agent import AgentSettings

if TYPE_CHECKING:
    import pytest


def test_agent_settings_migrate_legacy_speaker_model() -> None:
    settings = AgentSettings.model_validate({"speaker_model": "qwen_tts"})

    assert settings.tts.provider == "qwen_tts"
    assert settings.speaker_model == "qwen_tts"
    assert "speaker_model" not in settings.model_dump()


def test_agent_settings_tts_provider_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "qwen_tts")

    settings = AgentSettings.model_validate({})

    assert settings.tts.provider == "qwen_tts"

# pyright: reportPrivateUsage=false

from __future__ import annotations

from lab.profile.schema import Profile
from lab.service_context import ServiceContext


def test_to_character_settings_converts_structured_tts_emotions() -> None:
    profile = Profile.model_validate(
        {
            "profile": {"name": "baoqiao", "agent_name": "baoqiao"},
            "character": {
                "conf_name": "baoqiao-local",
                "conf_uid": "baoqiao-local-001",
                "live2d_model_name": "Baoqiao",
                "character_name": "Baoqiao",
                "avatar": "baoqiao.png",
                "human_name": "Human",
                "tts": {
                    "character_name": "baoqiao",
                    "emotions": {
                        "default": {
                            "path": "emotions/neutral/neutral_01.wav",
                            "ref_text": "",
                            "speaker_audio_path": "speaker/default.wav",
                        },
                        "happy": {
                            "path": "emotions/happy/happy_01.wav",
                            "ref_text": "happy ref text",
                            "speaker_audio_path": "speaker/happy.wav",
                        },
                    },
                },
            },
        }
    )

    settings = ServiceContext._to_character_settings(profile)

    assert settings is not None
    assert settings.tts_config.emotions["default"].path == "emotions/neutral/neutral_01.wav"
    assert settings.tts_config.emotions["default"].ref_text == ""
    assert settings.tts_config.emotions["default"].speaker_audio_path == "speaker/default.wav"
    assert settings.tts_config.emotions["happy"].path == "emotions/happy/happy_01.wav"
    assert settings.tts_config.emotions["happy"].ref_text == "happy ref text"
    assert settings.tts_config.emotions["happy"].speaker_audio_path == "speaker/happy.wav"

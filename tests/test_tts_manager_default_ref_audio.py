# pyright: reportPrivateUsage=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from pathlib import Path

from lab.config_manager.vtuber import CharacterSettings, TTSConfig
from lab.conversations.tts_manager import _resolve_gsv_lite_speaker_audio_path, _resolve_ref_audio_and_text
from lab.profile.schema import TTSConfig as ProfileTTSConfig


def test_resolve_ref_audio_and_text_prefers_matching_emotion(tmp_path: Path, monkeypatch) -> None:
    model_dir = tmp_path / "models" / "gptsovits" / "baoqiao" / "emotions"
    model_dir.mkdir(parents=True)
    happy_ref = model_dir / "happy.wav"
    happy_ref.write_bytes(b"wav")
    default_ref = model_dir / "neutral.wav"
    default_ref.write_bytes(b"wav")

    monkeypatch.chdir(tmp_path)

    character = CharacterSettings(
        tts_config=TTSConfig(
            character_name="baoqiao",
            emotions={
                "default": {"path": "emotions/neutral.wav", "ref_text": ""},
                "happy": {"path": "emotions/happy.wav", "ref_text": "happy ref text"},
            },
        )
    )

    ref_audio, ref_text = _resolve_ref_audio_and_text(character, emotion_keys=["happy"])

    assert ref_audio == str(Path("models/gptsovits/baoqiao/emotions/happy.wav"))
    assert ref_text == "happy ref text"


def test_resolve_ref_audio_and_text_uses_gsv_lite_reference_directory(tmp_path: Path, monkeypatch) -> None:
    model_dir = tmp_path / "models" / "gsv-tts-lite" / "baoqiao" / "emotions"
    model_dir.mkdir(parents=True)
    happy_ref = model_dir / "happy.wav"
    happy_ref.write_bytes(b"wav")

    monkeypatch.chdir(tmp_path)

    character = CharacterSettings(
        tts_config=TTSConfig(
            character_name="baoqiao",
            emotions={
                "default": {"path": "emotions/neutral.wav", "ref_text": ""},
                "happy": {"path": "emotions/happy.wav", "ref_text": "happy ref text"},
            },
        )
    )

    ref_audio, ref_text = _resolve_ref_audio_and_text(character, emotion_keys=["happy"], tts_provider="gsv_lite")

    assert ref_audio == str(Path("models/gsv-tts-lite/baoqiao/emotions/happy.wav"))
    assert ref_text == "happy ref text"


def test_resolve_ref_audio_and_text_falls_back_to_gptsovits_for_gsv_lite(tmp_path: Path, monkeypatch) -> None:
    model_dir = tmp_path / "models" / "gptsovits" / "baoqiao" / "emotions"
    model_dir.mkdir(parents=True)
    default_ref = model_dir / "neutral.wav"
    default_ref.write_bytes(b"wav")

    monkeypatch.chdir(tmp_path)

    character = CharacterSettings(
        tts_config=TTSConfig(
            character_name="baoqiao",
            emotions={"default": {"path": "emotions/neutral.wav", "ref_text": "neutral ref"}},
        )
    )

    ref_audio, ref_text = _resolve_ref_audio_and_text(character, emotion_keys=None, tts_provider="gsv_lite")

    assert ref_audio == str(Path("models/gptsovits/baoqiao/emotions/neutral.wav"))
    assert ref_text == "neutral ref"


def test_resolve_ref_audio_and_text_falls_back_to_first_emotion_without_ref_text(tmp_path: Path, monkeypatch) -> None:
    model_dir = tmp_path / "models" / "gptsovits" / "baoqiao" / "emotions"
    model_dir.mkdir(parents=True)
    first_ref = model_dir / "neutral.wav"
    first_ref.write_bytes(b"wav")

    monkeypatch.chdir(tmp_path)

    character = CharacterSettings(
        tts_config=TTSConfig(
            character_name="baoqiao",
            emotions={
                "neutral": "emotions/neutral.wav",
                "sad": {"path": "emotions/sad.wav", "ref_text": "sad ref text"},
            },
        )
    )

    ref_audio, ref_text = _resolve_ref_audio_and_text(character, emotion_keys=["happy"])

    assert ref_audio == str(Path("models/gptsovits/baoqiao/emotions/neutral.wav"))
    assert ref_text is None


def test_resolve_ref_audio_and_text_returns_none_when_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    character = CharacterSettings(
        tts_config=TTSConfig(
            character_name="baoqiao",
            emotions={"default": "emotions/neutral.wav"},
        )
    )

    ref_audio, ref_text = _resolve_ref_audio_and_text(character, emotion_keys=["happy"])

    assert ref_audio is None
    assert ref_text is None


def test_resolve_ref_audio_and_text_returns_none_when_emotions_empty() -> None:
    character = CharacterSettings(
        tts_config=TTSConfig(
            character_name="baoqiao",
            emotions={},
        )
    )

    ref_audio, ref_text = _resolve_ref_audio_and_text(character, emotion_keys=["happy"])

    assert ref_audio is None
    assert ref_text is None


def test_profile_tts_config_accepts_legacy_and_structured_emotions() -> None:
    config = ProfileTTSConfig.model_validate(
        {
            "character_name": "baoqiao",
            "emotions": {
                "default": "emotions/neutral.wav",
                "happy": {
                    "path": "emotions/happy.wav",
                    "ref_text": "happy ref text",
                    "speaker_audio_path": "speaker/happy.wav",
                },
            },
        }
    )

    assert config.emotions["default"].path == "emotions/neutral.wav"
    assert config.emotions["default"].ref_text == ""
    assert config.emotions["default"].speaker_audio_path == ""
    assert config.emotions["happy"].path == "emotions/happy.wav"
    assert config.emotions["happy"].ref_text == "happy ref text"
    assert config.emotions["happy"].speaker_audio_path == "speaker/happy.wav"


def test_resolve_gsv_lite_speaker_audio_path_prefers_matching_emotion(tmp_path: Path, monkeypatch) -> None:
    speaker_dir = tmp_path / "models" / "gsv-tts-lite" / "baoqiao" / "speaker"
    speaker_dir.mkdir(parents=True)
    happy_speaker = speaker_dir / "happy.wav"
    happy_speaker.write_bytes(b"wav")

    monkeypatch.chdir(tmp_path)

    character = CharacterSettings(
        tts_config=TTSConfig(
            character_name="baoqiao",
            emotions={
                "default": {
                    "path": "emotions/neutral.wav",
                    "ref_text": "",
                    "speaker_audio_path": "speaker/default.wav",
                },
                "happy": {
                    "path": "emotions/happy.wav",
                    "ref_text": "happy ref text",
                    "speaker_audio_path": "speaker/happy.wav",
                },
            },
        )
    )

    speaker_audio = _resolve_gsv_lite_speaker_audio_path(character, emotion_keys=["happy"], tts_provider="gsv_lite")

    assert speaker_audio == str(Path("models/gsv-tts-lite/baoqiao/speaker/happy.wav"))

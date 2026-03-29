from __future__ import annotations

from pathlib import Path

from lab.config_manager import XnneHangLabSettings
from lab.config_manager.validators import validate_all


def _base_settings(tmp_path: Path) -> XnneHangLabSettings:
    settings = XnneHangLabSettings()  # pyright: ignore[reportCallIssue]
    settings.root.root_dir = str(tmp_path)
    settings.agent.memory_agent_profile = ""
    settings.agent.memory_chat_profile = "profiles/congyin.toml"
    return settings


def _write_memory_chat_profile(profiles_dir: Path) -> None:
    (profiles_dir / "congyin.toml").write_text(
        """
[profile]
name = "congyin"
agent_name = "congyin"
""".strip(),
        encoding="utf-8",
    )


def test_validate_requires_memory_agent_profile() -> None:
    settings = _base_settings(Path.cwd())

    errors = validate_all(settings)

    assert any("[agent.memory_agent_profile]" in err for err in errors)
    assert any("active profile" in err for err in errors)


def test_validate_requires_character_in_memory_agent_profile(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "vtuber.toml").write_text(
        """
[profile]
name = "vtuber"
agent_name = "vtuber"

[prompt]
persona = "prompts/characters/elaina.md"
format = "prompts/formats/emotion_bracket.md"
""".strip(),
        encoding="utf-8",
    )
    (profiles_dir / "congyin.toml").write_text(
        """
[profile]
name = "congyin"
agent_name = "congyin"
""".strip(),
        encoding="utf-8",
    )

    settings = _base_settings(tmp_path)
    settings.agent.memory_agent_profile = "profiles/vtuber.toml"

    errors = validate_all(settings)

    assert any("缺少 [character]" in err for err in errors)


def test_validate_rejects_duplicate_live2d_appearance_preset_keys(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "vtuber.toml").write_text(
        """
[profile]
name = "vtuber"
agent_name = "vtuber"

[character]
conf_name = "vtuber-local"
conf_uid = "vtuber-local-001"
live2d_model_name = "Baoqiao"
character_name = "VTuber"
avatar = "avatar.png"
human_name = "Human"

[prompt]
persona = "prompts/characters/elaina.md"
format = "prompts/formats/emotion_bracket.md"

[plugins]
enabled = ["live2d_control"]

[[plugins.live2d_control.appearance_presets]]
key = "默认"
description = "A"

[[plugins.live2d_control.appearance_presets]]
key = "默认"
description = "B"
""".strip(),
        encoding="utf-8",
    )
    (profiles_dir / "congyin.toml").write_text(
        """
[profile]
name = "congyin"
agent_name = "congyin"
""".strip(),
        encoding="utf-8",
    )

    settings = _base_settings(tmp_path)
    settings.agent.memory_agent_profile = "profiles/vtuber.toml"

    errors = validate_all(settings)

    assert any("[plugins.live2d_control]" in err for err in errors)
    assert any("duplicate key" in err for err in errors)


def test_validate_uses_active_profile_character_tts_model(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "vtuber.toml").write_text(
        """
[profile]
name = "vtuber"
agent_name = "vtuber"

[character]
conf_name = "vtuber-local"
conf_uid = "vtuber-local-001"
live2d_model_name = "Baoqiao"
character_name = "VTuber"
avatar = "avatar.png"
human_name = "Human"

[character.tts]
character_name = "baoqiao"

[prompt]
persona = "prompts/characters/elaina.md"
format = "prompts/formats/emotion_bracket.md"
""".strip(),
        encoding="utf-8",
    )
    _write_memory_chat_profile(profiles_dir)

    settings = _base_settings(tmp_path)
    settings.agent.memory_agent_profile = "profiles/vtuber.toml"

    errors = validate_all(settings)

    assert any("models" in err and "gptsovits" in err and "baoqiao" in err for err in errors)


def test_validate_rejects_disabled_sherpa_provider_selection(tmp_path: Path) -> None:
    settings = _base_settings(tmp_path)
    settings.asr.asr_model_provider = "sherpa"
    settings.package.sherpa_asr = False
    settings.package.qwen_asr = False

    errors = validate_all(settings)

    assert any('asr_model_provider = "sherpa"' in err for err in errors)
    assert any("package.sherpa_asr = false" in err for err in errors)


def test_validate_rejects_disabled_qwen_provider_selection(tmp_path: Path) -> None:
    settings = _base_settings(tmp_path)
    settings.asr.asr_model_provider = "qwen"
    settings.package.sherpa_asr = False
    settings.package.qwen_asr = False

    errors = validate_all(settings)

    assert any('asr_model_provider = "qwen"' in err for err in errors)
    assert any("package.qwen_asr = false" in err for err in errors)


def test_validate_rejects_disabled_qwen_tts_selection(tmp_path: Path) -> None:
    settings = _base_settings(tmp_path)
    settings.agent.speaker_model = "qwen_tts"
    settings.package.qwen_tts = False

    errors = validate_all(settings)

    assert any('speaker_model = "qwen_tts"' in err for err in errors)
    assert any("package.qwen_tts = false" in err for err in errors)

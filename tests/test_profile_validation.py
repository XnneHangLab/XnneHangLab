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

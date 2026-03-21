from __future__ import annotations

from pathlib import Path

from lab.config_manager import XnneHangLabSettings
from lab.server import _resolve_active_gpt_sovits_character


def _build_settings(tmp_path: Path) -> XnneHangLabSettings:
    settings = XnneHangLabSettings()  # pyright: ignore[reportCallIssue]
    settings.root.root_dir = str(tmp_path)
    settings.agent.memory_agent_profile = "profiles/vtuber.toml"
    return settings


def test_resolve_active_gpt_sovits_character_prefers_character_tts_name(tmp_path: Path) -> None:
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
""".strip(),
        encoding="utf-8",
    )

    settings = _build_settings(tmp_path)

    assert _resolve_active_gpt_sovits_character(settings) == "baoqiao"


def test_gpt_sovits_v2_ref_audio_base_dir_uses_active_profile_character(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from lab.api.routes import gpt_sovits_v2

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
""".strip(),
        encoding="utf-8",
    )

    settings = _build_settings(tmp_path)
    monkeypatch.setattr(gpt_sovits_v2, "load_settings_file", lambda *_args, **_kwargs: settings)

    assert gpt_sovits_v2._resolve_ref_audio_base_dir() == (tmp_path / "models" / "gptsovits" / "baoqiao").resolve()

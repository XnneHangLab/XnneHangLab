from __future__ import annotations

import tomllib
from pathlib import Path

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.config_manager.config import CURRENT_CONF_VERSION


def test_load_lab_settings_normalizes_conf_version(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    lab_toml = config_dir / "lab.toml"
    lab_toml.write_text('conf_version = "v0.0.1"\n', encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    settings = load_settings_file("lab.toml", XnneHangLabSettings)

    assert settings.conf_version == CURRENT_CONF_VERSION

    with lab_toml.open("rb") as file:
        saved = tomllib.load(file)

    assert saved["conf_version"] == CURRENT_CONF_VERSION

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def _load_script_module(script_name: str):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / script_name
    module_name = f"test_script_{script_name.replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reload_lab_setting_resets_to_seeded_providers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "lab.toml").write_text(
        """
[agent.chat_model]
llm_provider = "custom"
llm_model_name = "custom-chat"

[[agent.llm.providers]]
name = "custom"
llm_api_key = "secret"
llm_base_url = "https://custom.example/v1"
api_format = "chat_completion"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    module = _load_script_module("reload_lab_setting.py")
    module.main()

    with (config_dir / "lab.toml").open("rb") as file:
        saved = tomllib.load(file)

    assert saved["agent"]["chat_model"]["llm_provider"] == ""
    assert saved["agent"]["llm"]["providers"] == [
        {
            "name": "openai",
            "llm_api_key": "",
            "llm_base_url": "https://api.openai.com/v1",
            "api_format": "chat_completion",
        },
        {
            "name": "google",
            "llm_api_key": "",
            "llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "api_format": "chat_completion",
        },
    ]


def test_sync_apikey_overwrites_existing_provider_and_creates_missing_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "lab.toml").write_text(
        """
[agent.chat_model]
llm_provider = "openai"
llm_model_name = "before"

[[agent.llm.providers]]
name = "openai"
llm_api_key = ""
llm_base_url = "https://api.openai.com/v1"
api_format = "chat_completion"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "LLM_PROVIDERS_JSON",
        '{"providers":['
        '{"name":"openai","llm_api_key":"sk-openai"},'
        '{"name":"custom","llm_base_url":"https://custom.example/v1","llm_api_key":"sk-custom","api_format":"chat_completion"}'
        "]}",
    )
    monkeypatch.setenv("CHAT_MODEL_PROVIDER", "custom")
    monkeypatch.setenv("CHAT_MODEL_NAME", "custom-chat")

    module = _load_script_module("sync_apikey.py")
    module.main()

    with (config_dir / "lab.toml").open("rb") as file:
        saved = tomllib.load(file)

    assert saved["agent"]["chat_model"]["llm_provider"] == "custom"
    assert saved["agent"]["chat_model"]["llm_model_name"] == "custom-chat"
    assert saved["agent"]["llm"]["providers"] == [
        {
            "name": "openai",
            "llm_api_key": "sk-openai",
            "llm_base_url": "https://api.openai.com/v1",
            "api_format": "chat_completion",
        },
        {
            "name": "custom",
            "llm_api_key": "sk-custom",
            "llm_base_url": "https://custom.example/v1",
            "api_format": "chat_completion",
        },
    ]

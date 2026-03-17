from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path


class ProfileConfig(BaseModel):
    name: str
    description: str = ""
    agent_name: str = ""


class PromptConfig(BaseModel):
    persona: str | None = None
    format: str | None = None


class TTSPreprocessorConfig(BaseModel):
    """TTS text preprocessing configuration."""

    remove_special_char: bool = True
    ignore_brackets: bool = True
    ignore_parentheses: bool = True
    ignore_asterisks: bool = True
    ignore_angle_brackets: bool = True


class CharacterConfig(BaseModel):
    """VTuber-only character identity and Live2D configuration."""

    conf_name: str = ""
    conf_uid: str = ""
    live2d_model_name: str | None = None
    character_name: str = ""
    avatar: str = ""
    human_name: str = "Human"
    tts_preprocessor: TTSPreprocessorConfig = Field(default_factory=TTSPreprocessorConfig)


class PluginsConfig(BaseModel):
    enabled: list[str] = Field(default_factory=list)
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class Profile(BaseModel):
    profile: ProfileConfig
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    character: CharacterConfig | None = None

    @classmethod
    def from_toml(cls, path: Path) -> Profile:
        with path.open("rb") as f:
            raw = tomllib.load(f)

        plugins_raw = raw.get("plugins", {})
        enabled = plugins_raw.get("enabled", [])
        overrides: dict[str, dict[str, Any]] = {
            k: v for k, v in plugins_raw.items() if k != "enabled" and isinstance(v, dict)
        }
        raw["plugins"] = {"enabled": enabled, "overrides": overrides}
        return cls.model_validate(raw)

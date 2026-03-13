from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path


class ContextConfig(BaseModel):
    memory_search: bool = True
    diary_summary: bool = False


class ProfileConfig(BaseModel):
    name: str
    description: str = ""
    agent_name: str = ""


class PromptConfig(BaseModel):
    persona: str | None = None
    format: str | None = None


class PluginsConfig(BaseModel):
    enabled: list[str] = Field(default_factory=list)
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class Profile(BaseModel):
    profile: ProfileConfig
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)

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

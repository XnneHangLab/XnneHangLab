from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from lab.plugin.loader import PluginLoader
from lab.plugins.live2d_control import Live2DControlPluginConfig
from lab.tools.plugin import ToolPlugin
from lab.tools.types import AgentContext


def test_live2d_control_config_rejects_blank_and_duplicate_keys() -> None:
    with pytest.raises(ValidationError):
        Live2DControlPluginConfig.model_validate({"appearance_presets": [{"key": "   ", "description": "blank"}]})

    with pytest.raises(ValidationError):
        Live2DControlPluginConfig.model_validate(
            {
                "appearance_presets": [
                    {"key": "default", "description": "A"},
                    {"key": "default", "description": "B"},
                ]
            }
        )


def test_live2d_control_runtime_reads_appearance_presets() -> None:
    async def _load_plugin() -> ToolPlugin | None:
        loader = PluginLoader()
        ctx = AgentContext(
            workspace_root=Path.cwd(),
            extra={"live2d_emo_map": {"default": "expr_default", "hidden_hair": "expr_hidden"}},
        )
        loaded = await loader.load(
            "live2d_control",
            profile_overrides={
                "appearance_presets": [
                    {"key": "default", "description": "full style"},
                    {"key": "hidden_hair", "description": "clean look"},
                ]
            },
            ctx=ctx,
        )
        if loaded is None:
            return None
        assert isinstance(loaded, ToolPlugin)
        return loaded

    plugin = asyncio.run(_load_plugin())

    assert plugin is not None
    prompt_segments = plugin.get_prompt_segments()
    assert len(prompt_segments) == 1
    assert "full style" in prompt_segments[0].content
    assert "hidden_hair" in prompt_segments[0].content

    tools = {tool.name: tool for tool in plugin.get_tools()}
    result = asyncio.run(
        tools["set_live2d_appearance"].execute(
            {"appearance_key": "hidden_hair"},
            AgentContext(workspace_root=Path.cwd(), extra={}),
        )
    )
    assert result.ok is True
    assert "hidden_hair" in result.text

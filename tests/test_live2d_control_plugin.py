from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from lab.plugin.loader import PluginLoader
from lab.plugins.live2d_control import Live2DControlPluginConfig
from lab.tools.types import AgentContext


def test_live2d_control_config_rejects_blank_and_duplicate_keys() -> None:
    with pytest.raises(ValidationError):
        Live2DControlPluginConfig.model_validate(
            {"appearance_presets": [{"key": "   ", "description": "blank"}]}
        )

    with pytest.raises(ValidationError):
        Live2DControlPluginConfig.model_validate(
            {
                "appearance_presets": [
                    {"key": "默认", "description": "A"},
                    {"key": "默认", "description": "B"},
                ]
            }
        )


def test_live2d_control_runtime_reads_appearance_presets() -> None:
    async def _load_plugin():
        loader = PluginLoader()
        ctx = AgentContext(
            workspace_root=Path.cwd(),
            extra={"live2d_emo_map": {"默认": "expr_default", "隐藏披发": "expr_hidden"}},
        )
        return await loader.load(
            "live2d_control",
            profile_overrides={
                "appearance_presets": [
                    {"key": "默认", "description": "完整造型"},
                    {"key": "隐藏披发", "description": "更利落"},
                ]
            },
            ctx=ctx,
        )

    plugin = asyncio.run(_load_plugin())

    assert plugin is not None
    prompt_segments = plugin.get_prompt_segments()
    assert len(prompt_segments) == 1
    assert "完整造型" in prompt_segments[0].content
    assert "隐藏披发" in prompt_segments[0].content

    tools = {tool.name: tool for tool in plugin.get_tools()}
    result = asyncio.run(
        tools["set_live2d_appearance"].execute(
            {"appearance_key": "隐藏披发"},
            AgentContext(workspace_root=Path.cwd(), extra={}),
        )
    )
    assert result.ok is True
    assert "隐藏披发" in result.text

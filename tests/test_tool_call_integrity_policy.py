from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from lab.plugin.loader import PluginLoader
from lab.plugins.tool_call_integrity import ToolCallIntegrityPlugin
from lab.profile.system_prompt_builder import SystemPromptBuilder
from lab.tools import GetDatetimeTool, ToolManager

if TYPE_CHECKING:
    from pathlib import Path


def test_tool_call_integrity_plugin_loads_as_policy() -> None:
    plugin = asyncio.run(PluginLoader().load("tool_call_integrity"))

    assert isinstance(plugin, ToolCallIntegrityPlugin)
    segments = plugin.get_prompt_segments()
    assert len(segments) == 1
    assert segments[0].name == "工具调用完整性"
    assert "[list_dir ...]" in segments[0].content


def test_tool_call_integrity_segment_is_included_in_system_prompt(tmp_path: Path) -> None:
    tool_manager = ToolManager()
    tool_manager.register_builtin(GetDatetimeTool())
    plugin = ToolCallIntegrityPlugin()

    prompt = SystemPromptBuilder(tmp_path).build(
        persona_path=None,
        format_path=None,
        skills=[],
        tool_manager=tool_manager,
        tool_prompt_segments=plugin.get_prompt_segments(),
        agent_name="tester",
    )

    assert "工具调用完整性" in prompt
    assert "[list_dir ...]" in prompt
    assert "get_datetime" in prompt

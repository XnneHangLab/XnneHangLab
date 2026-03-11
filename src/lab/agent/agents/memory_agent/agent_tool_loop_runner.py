from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from lab.agent.agent_tool_loop import AgentToolLoop


@dataclass(frozen=True)
class AgentToolLoopRunResult:
    """Result of a tool loop run."""

    trace_json: str
    final_text: str


class AgentToolLoopRunner:
    """Run AgentToolLoop for MemoryAgent — no MCP dependency.

    Drop-in replacement for ToolRunner when MCP is not needed.
    """

    def __init__(self, *, agent_tool_loop: AgentToolLoop) -> None:
        self._loop = agent_tool_loop

    async def run_tool_loop_if_enabled(
        self,
        *,
        enable_tool: bool,
        tool_system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> AgentToolLoopRunResult:
        """Run tool loop if enabled; otherwise return empty result."""
        if not enable_tool:
            return AgentToolLoopRunResult(trace_json="(无)", final_text="")

        if not self._loop.tool_manager.list_tools_schema():
            logger.info("[AgentToolLoopRunner] no tools available; skipping tool loop.")
            return AgentToolLoopRunResult(trace_json="(无)", final_text="")

        full_messages, final_text = await self._loop.run(
            messages=messages,
            system_prompt=tool_system_prompt,
        )

        tool_trace = [m for m in full_messages if m.get("role") == "tool"]
        trace_json = json.dumps(tool_trace, ensure_ascii=False, indent=2)

        return AgentToolLoopRunResult(trace_json=trace_json, final_text=final_text)

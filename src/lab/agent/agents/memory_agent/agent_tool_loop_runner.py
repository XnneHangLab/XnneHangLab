from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from .types import ImagePayload

if TYPE_CHECKING:
    from lab.agent.agent_tool_loop import AgentToolLoop


@dataclass(frozen=True)
class AgentToolLoopRunResult:
    """Result of a tool loop run."""

    trace_json: str
    final_text: str
    tool_image: ImagePayload | None


class AgentToolLoopRunner:
    """Run AgentToolLoop for MemoryAgent — no MCP dependency.

    Drop-in replacement for ToolRunner when MCP is not needed.
    """

    def __init__(self, *, agent_tool_loop: AgentToolLoop) -> None:
        """Initialize the runner.

        Args:
            agent_tool_loop: Tool loop implementation used to execute builtin tools.

        Returns:
            None.
        """
        self._loop = agent_tool_loop
        self._last_screenshot_image: ImagePayload | None = None

    async def run_tool_loop_if_enabled(
        self,
        *,
        enable_tool: bool,
        tool_system_prompt: str,
        messages: list[dict[str, Any]],
        reuse_last_screenshot: bool,
    ) -> AgentToolLoopRunResult:
        """Run the tool loop or reuse the previous screenshot when requested.

        Args:
            enable_tool: Whether tool use is enabled for this turn.
            tool_system_prompt: System prompt for the tool-calling model.
            messages: Tool-loop input messages excluding the system prompt.
            reuse_last_screenshot: Whether the caller wants to reuse the previous screenshot directly.

        Returns:
            The tool trace, final tool-loop text, and the latest screenshot payload if available.
        """
        if not enable_tool:
            return AgentToolLoopRunResult(trace_json="(无)", final_text="", tool_image=None)

        if reuse_last_screenshot and self._last_screenshot_image is not None:
            return AgentToolLoopRunResult(
                trace_json="(复用上一张截图，无新增 tool trace)",
                final_text="",
                tool_image=self._last_screenshot_image,
            )

        if not self._loop.tool_manager.list_tools_schema():
            logger.info("[AgentToolLoopRunner] no tools available; skipping tool loop.")
            return AgentToolLoopRunResult(trace_json="(无)", final_text="", tool_image=None)

        full_messages, final_text, captured_images = await self._loop.run(
            messages=messages,
            system_prompt=tool_system_prompt,
        )

        tool_trace = [m for m in full_messages if m.get("role") == "tool"]
        trace_json = json.dumps(tool_trace, ensure_ascii=False, indent=2)

        tool_image = self._last_screenshot_image
        if captured_images:
            b64, mime = captured_images[-1]
            tool_image = ImagePayload(label="tool1", b64=b64, mime=mime, source="tool")
            self._last_screenshot_image = tool_image

        return AgentToolLoopRunResult(trace_json=trace_json, final_text=final_text, tool_image=tool_image)

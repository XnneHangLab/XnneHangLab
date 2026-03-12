from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

if TYPE_CHECKING:
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM, OpenAIMessage
    from lab.tools import AgentContext, ToolManager


class AgentToolLoop:
    """Lightweight tool-calling loop backed by ToolManager only.

    No MCP, no ConversationState, no ToolRegistry.
    Suitable for any agent that only needs ToolManager-registered tools.
    """

    def __init__(
        self,
        *,
        llm: AsyncLLM,
        tool_manager: ToolManager,
        agent_context: AgentContext,
        max_steps: int = 6,
    ) -> None:
        """Initialize the tool loop.

        Args:
            llm: Tool-calling model used to plan tool invocations.
            tool_manager: Registry and executor for builtin tools.
            agent_context: Runtime context passed into each tool execution.
            max_steps: Maximum number of tool-calling rounds per run.

        Returns:
            None.
        """
        self._llm = llm
        self._tool_manager = tool_manager
        self._agent_context = agent_context
        self._max_steps = max_steps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def tool_manager(self) -> ToolManager:
        """Return the bound tool manager.

        Args:
            None.

        Returns:
            The tool manager used by this loop.
        """
        return self._tool_manager

    async def run(
        self,
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
    ) -> tuple[list[dict[str, Any]], str, list[tuple[str, str]]]:
        """Run the tool loop and collect screenshot payloads out of band.

        Args:
            messages: Conversation messages excluding the system prompt.
            system_prompt: System prompt for the tool-calling model.

        Returns:
            The full tool-loop transcript, the final assistant text, and captured screenshots as `(b64, mime)` pairs.
        """
        full_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, *messages]
        tools = self._tool_manager.list_tools_schema()
        final_text = ""
        captured_images: list[tuple[str, str]] = []

        for step in range(self._max_steps):
            completion = await self._llm.tool_completion(
                messages=cast("list[OpenAIMessage]", full_messages),
                tools=tools,
                tool_choice="auto",
                system=None,
            )

            assistant_msg = completion.choices[0].message
            tool_calls = getattr(assistant_msg, "tool_calls", None)
            final_text = assistant_msg.content or ""

            if not tool_calls:
                full_messages.append({"role": "assistant", "content": final_text})
                break

            logger.info(f"[AgentToolLoop step={step}] tool_calls={[tc.function.name for tc in tool_calls]}")

            assistant_dict: dict[str, Any] = {
                "role": "assistant",
                "content": final_text,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
            full_messages.append(assistant_dict)

            results = await asyncio.gather(*(self._call_tool(tc) for tc in tool_calls))

            for tc, result in zip(tool_calls, results, strict=True):
                if result["captured_image"] is not None:
                    captured_images.append(result["captured_image"])
                full_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result["content"],
                    }
                )

        return full_messages, final_text, captured_images

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _call_tool(self, tc: Any) -> dict[str, Any]:
        """Execute a single tool call via ToolManager."""
        name = tc.function.name
        args_json = tc.function.arguments or "{}"

        logger.info(f"[AgentToolLoop] executing {name}({args_json[:200]})")

        try:
            result = await self._tool_manager.call_tool(name, args_json, self._agent_context)
            content = self._tool_result_to_text(result.text, result.data, result.error, result.ok)
            captured_image = self._extract_captured_image(result.data)
            if captured_image is not None:
                content = "[screenshot captured]"
            return {"name": name, "content": content, "captured_image": captured_image}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            logger.warning(f"[AgentToolLoop] tool {name} failed: {err}")
            return {"name": name, "content": f"tool_error: {err}", "captured_image": None}

    @staticmethod
    def _extract_captured_image(data: dict[str, Any] | None) -> tuple[str, str] | None:
        """Extract a screenshot payload from tool data when present."""
        if not isinstance(data, dict):
            return None

        image_b64 = data.get("image_b64")
        if not isinstance(image_b64, str) or not image_b64:
            return None

        mime = data.get("mime")
        if not isinstance(mime, str) or not mime:
            mime = "image/jpeg"
        return image_b64, mime

    @staticmethod
    def _tool_result_to_text(
        text: str,
        data: dict[str, Any] | None,
        error: str | None,
        ok: bool,
    ) -> str:
        if ok:
            if text:
                return text
            if data:
                return json.dumps(data, ensure_ascii=False)
            return "(no output)"
        if error:
            return f"tool_error: {error}"
        return "tool_error: unknown tool failure"

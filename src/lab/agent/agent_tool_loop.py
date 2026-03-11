from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
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
        self._llm = llm
        self._tool_manager = tool_manager
        self._agent_context = agent_context
        self._max_steps = max_steps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def tool_manager(self) -> ToolManager:
        return self._tool_manager

    async def run(
        self,
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
    ) -> tuple[list[dict[str, Any]], str]:
        """Run a ToolManager-only tool loop and return full messages plus final text."""
        full_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, *messages]
        tools = self._tool_manager.list_tools_schema()
        final_text = ""

        for step in range(self._max_steps):
            completion = await self._llm.tool_completion(
                messages=full_messages,  # AsyncLLM accepts dict messages via normalize_messages()
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
                full_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result["content"],
                        "name": result["name"],
                    }
                )

        return full_messages, final_text

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _call_tool(self, tc: Any) -> dict[str, str]:
        """Execute a single tool call via ToolManager."""
        name = tc.function.name
        args_json = tc.function.arguments or "{}"

        logger.info(f"[AgentToolLoop] executing {name}({args_json[:200]})")

        try:
            result = await self._tool_manager.call_tool(name, args_json, self._agent_context)
            content = self._tool_result_to_text(result.text, result.data, result.error, result.ok)
            return {"name": name, "content": content}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            logger.warning(f"[AgentToolLoop] tool {name} failed: {err}")
            return {"name": name, "content": f"tool_error: {err}"}

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

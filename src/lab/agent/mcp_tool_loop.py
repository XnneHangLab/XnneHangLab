from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from loguru import logger

from lab.mcp import ToolCallLike, ToolMessage, ToolRegistry, ToolTraceItem

# These helpers exist in your codebase (same as your MCP demo).
from lab.mcp.util import call_with_short_retry, dump_openai_msg, prompt_result_to_text  # type: ignore

if TYPE_CHECKING:
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.mcp import FastMcpRouter


class McpToolLoopRunner:
    """Run an OpenAI tool-calling loop, execute MCP tools, and return tool_trace.

    Protocol notes:
    - After an assistant message with `tool_calls`, you MUST append all tool messages immediately,
      with no interleaving user/system messages, otherwise OpenAI will 400.
    """

    def __init__(self, *, tool_llm: AsyncLLM, mcp: FastMcpRouter) -> None:
        self.tool_llm = tool_llm
        self.mcp = mcp

    async def _execute_tool_call(
        self,
        tool_call: ToolCallLike,
        *,
        user_input: str,
        tool_output_as_user_prompt: bool = True,
    ) -> tuple[ToolMessage, list[dict[str, object]], ToolTraceItem]:
        full_name = tool_call.function.name

        # 1) args strong-typed parse
        parsed = ToolRegistry.parse_args(full_name, tool_call.function.arguments)
        args_dict = parsed.args_model.model_dump(exclude_none=True)

        # 2) call MCP tool
        try:
            result_obj = await self.mcp.call_tool(full_name=full_name, args=args_dict)
            result_model = ToolRegistry.parse_result(full_name, result_obj)
            tool_text = ToolRegistry.tool_content_for_tool_model(full_name, result_model)

            tool_msg = ToolMessage(content=tool_text, tool_call_id=tool_call.id)
            trace = ToolRegistry.trace_item(parsed, result_model, ok=True, error=None)

        except Exception as e:  # don't break tool loop
            err = f"{type(e).__name__}: {e}"
            tool_msg = ToolMessage(content=err, tool_call_id=tool_call.id)
            trace = ToolTraceItem(
                server=parsed.server,
                name=parsed.name,
                args=args_dict,
                raw_result={},
                ok=False,
                error=err,
            )

        # 3) optional chaining prompts
        extra_msgs: list[dict[str, object]] = []
        if tool_output_as_user_prompt and trace.ok:
            if parsed.full_name == "timeemi__get_date_and_time":
                dt = trace.raw_result.get("datetime")
                if isinstance(dt, str):
                    pr = await self.mcp.get_prompt(
                        full_name=parsed.full_name,
                        prompt_name="convert_time_readable",
                        args={"time_str": dt},
                    )
                    extra_msgs.append({"role": "user", "content": prompt_result_to_text(pr)})

            if parsed.full_name == "timeemi__roll_dice":
                nums = trace.raw_result.get("numbers")
                if isinstance(nums, list) and all(isinstance(x, int) for x in nums):  # type: ignore
                    pr = await self.mcp.get_prompt(
                        full_name=parsed.full_name,
                        prompt_name="convert_list_int_readable",
                        args={"numbers": nums},
                    )
                    extra_msgs.append({"role": "user", "content": prompt_result_to_text(pr)})

            if parsed.full_name == "timeemi__roll_dice_by_current_time":
                unit = trace.raw_result.get("unit")
                if isinstance(unit, str):
                    pr = await self.mcp.get_prompt(
                        full_name=parsed.full_name,
                        prompt_name="convert_time_unit_readable",
                        args={"unit": unit},
                    )
                    extra_msgs.append({"role": "user", "content": prompt_result_to_text(pr)})

        return tool_msg, extra_msgs, trace

    async def run_tool_loop(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, object]],
        available_tools: list[dict[str, object]],
        max_steps: int = 6,
        max_parallel_tools: int = 6,
        tool_output_as_user_prompt: bool = True,
        debug: bool = True,
    ) -> tuple[list[dict[str, object]], list[ToolTraceItem]]:
        """Tool model loop (non-stream) with parallel tool execution and caching."""

        tool_loop_messages: list[dict[str, object]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]
        tool_trace: list[ToolTraceItem] = []

        cache: dict[str, tuple[str, ToolTraceItem, list[dict[str, object]]]] = {}

        def _sig(full_name: str, args_dict: dict[str, object]) -> str:
            return full_name + "::" + json.dumps(args_dict, ensure_ascii=False, sort_keys=True)

        # user_input: last user message content (best effort)
        user_input = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_input = str(m.get("content", ""))
                break

        for step in range(max_steps):
            resp = await call_with_short_retry(  # type: ignore[arg-type]
                lambda: self.tool_llm.tool_completion(
                    messages=tool_loop_messages,  # includes system already
                    tools=available_tools,  # OpenAI schema from MCP
                    tool_choice="auto",
                ),
                max_retries=2,
            )

            assistant_msg = resp.choices[0].message  # type: ignore[attr-defined]
            tool_loop_messages.append(dump_openai_msg(assistant_msg))  # type: ignore[arg-type]

            tool_calls = getattr(assistant_msg, "tool_calls", None)  # type: ignore[attr-defined]
            if debug:
                names = [tc.function.name for tc in (tool_calls or [])]  # type: ignore
                logger.info(f"[ToolLoop step={step}] tool_calls={names}")

            if not tool_calls:
                break

            tool_calls_all = list(tool_calls)
            tool_calls_exec = tool_calls_all[:max_parallel_tools]
            tool_calls_skipped = tool_calls_all[max_parallel_tools:]

            # 1) schedule real tool calls (dedupe by signature)
            tasks: list[asyncio.Task[tuple[ToolMessage, list[dict[str, object]], ToolTraceItem]]] = []
            planned: list[tuple[ToolCallLike, str]] = []

            for tc in tool_calls_exec:
                full_name = tc.function.name
                parsed = ToolRegistry.parse_args(full_name, tc.function.arguments)
                args_dict = parsed.args_model.model_dump(exclude_none=True)
                sig = _sig(full_name, args_dict)
                planned.append((tc, sig))

                if sig in cache:
                    continue

                tasks.append(
                    asyncio.create_task(
                        self._execute_tool_call(
                            tc,
                            user_input=user_input,
                            tool_output_as_user_prompt=tool_output_as_user_prompt,
                        )
                    )
                )

            if tasks:
                results = await asyncio.gather(*tasks)
                for tool_msg, extra_msgs, trace in results:
                    full_name = f"{trace.server}__{trace.name}"
                    sig = _sig(full_name, trace.args)
                    cache[sig] = (tool_msg.content, trace, extra_msgs)

            # 2) build tool messages (MUST be consecutive)
            tool_msgs_to_append: list[dict[str, object]] = []
            extra_msgs_to_append: list[dict[str, object]] = []

            for tc, sig in planned:
                if sig in cache:
                    cached_content, cached_trace, cached_extra = cache[sig]
                    tool_msgs_to_append.append(
                        ToolMessage(content=cached_content, tool_call_id=tc.id).model_dump(exclude_none=True)
                    )

                    if cached_trace not in tool_trace:
                        tool_trace.append(cached_trace)

                    for em in cached_extra:
                        if em not in extra_msgs_to_append:
                            extra_msgs_to_append.append(em)

                else:
                    tool_msgs_to_append.append(
                        ToolMessage(content="tool_error: missing result", tool_call_id=tc.id).model_dump(
                            exclude_none=True
                        )
                    )

            for tc in tool_calls_skipped:
                tool_msgs_to_append.append(
                    ToolMessage(
                        content="skipped_due_to_max_parallel_tools",
                        tool_call_id=tc.id,
                    ).model_dump(exclude_none=True)
                )

            tool_loop_messages.extend(tool_msgs_to_append)
            tool_loop_messages.extend(extra_msgs_to_append)

        return tool_loop_messages, tool_trace

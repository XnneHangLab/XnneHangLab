from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from loguru import logger

from lab.mcp import (
    DEFAULT_RETRY_HINT,
    TOOL_RETRY_HINTS,
    ConversationState,
    ScreenShotResult,
    ToolCallLike,
    ToolMessage,
    ToolRegistry,
    ToolTraceItem,
    build_tool_context,
)

# These helpers exist in your codebase (same as your MCP demo).
from lab.mcp.util import call_with_short_retry, dump_openai_msg, prompt_result_to_text  # type: ignore

if TYPE_CHECKING:
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.config_manager import ToolContextConfig
    from lab.mcp import FastMcpRouter


class McpToolLoopRunner:
    """Run an OpenAI tool-calling loop, execute MCP tools, and return tool_trace.

    Protocol notes:
    - After an assistant message with `tool_calls`, you MUST append all tool messages immediately,
      with no interleaving user/system messages, otherwise OpenAI will 400.
    """

    def __init__(self, *, tool_llm: AsyncLLM, mcp: FastMcpRouter, tool_context_config: ToolContextConfig) -> None:
        self.tool_llm = tool_llm
        self.mcp = mcp
        self._blob_store: dict[str, dict[str, object]] = {}  # call_id -> {"mime":..., "b64":...}
        self.state = ConversationState()
        self.tool_ctx_cfg = tool_context_config

    def _snip(self, s: str, n: int = 1200) -> str:
        """截断字符串，保留前 n 个字符，加省略号"""
        ss = (s or "").strip()
        if len(ss) <= n:
            return ss
        return ss[:n] + f"\n...(preview truncated, {len(ss)} chars total)..."

    async def _execute_tool_call(
        self,
        tool_call: ToolCallLike,
        *,
        user_input: str,
        tool_output_as_user_prompt: bool = True,
    ) -> tuple[ToolMessage, list[dict[str, object]], ToolTraceItem]:
        """
        执行单个 tool_call（强类型校验 + trace）。

        返回：
        - ToolMessage：回填给 Tool Model
        - extra_msgs：作为下一轮 Tool Model 的额外 user messages（用于链式）
        - ToolTraceItem：结构化摘要（给 Chat Model）
        """
        full_name = tool_call.function.name

        # 1) args 强校验
        parsed = ToolRegistry.parse_args(full_name, tool_call.function.arguments)
        args_dict = parsed.args_model.model_dump(exclude_none=True)

        # 2) 调工具
        try:
            result_obj = await self.mcp.call_tool(full_name=full_name, args=args_dict)
            result_model = ToolRegistry.parse_result(full_name, result_obj)
            if isinstance(result_model, ScreenShotResult):
                # 调用了截图工具，存 blob，不能直接放 base64 到消息里
                b64 = result_model.image_b64
                self._blob_store[tool_call.id] = {"mime": "image/jpeg", "b64": b64}

                # ToolMessage 给 Tool Model：只给短信息
                tool_msg = ToolMessage(
                    content=f"[screenshot captured] ref={tool_call.id} mime=image/jpeg b64_len={len(b64)}",
                    tool_call_id=tool_call.id,
                )

                # ToolTrace 给 Chat Model：只给 ref + 元信息
                trace = ToolRegistry.trace_item(
                    parsed,
                    ScreenShotResult(image_b64=""),  # 或者你直接手动构造 raw_result
                    ok=True,
                    error=None,
                )
                trace.raw_result = {
                    "image_ref": tool_call.id,
                    "mime": "image/jpeg",
                    "b64_len": len(b64),
                }
            else:
                # 普通工具调用
                tool_text = ToolRegistry.tool_content_for_tool_model(result_model)

                tool_msg = ToolMessage(content=tool_text, tool_call_id=tool_call.id)
                trace = ToolRegistry.trace_item(parsed, result_model, ok=True, error=None)

        except Exception as e:
            # 不让异常打断 tool loop：记录错误，tool_msg 回填错误文本
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

        # 3) 链式 extra prompt（可选）
        extra_msgs: list[dict[str, object]] = []
        if tool_output_as_user_prompt:
            if trace.ok:
                # 只对你已知工具做 prompt
                if parsed.full_name == "timeemi__get_date_and_time":
                    # 这里传 raw datetime 给 server prompt 模板（让 Tool Model/Chat Model 自己口语化）
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

                if parsed.full_name == "vision__screen_shot":
                    pr = await self.mcp.get_prompt(
                        full_name=parsed.full_name,
                        prompt_name="describe_image",
                        args={},
                    )
                    extra_msgs.append({"role": "user", "content": prompt_result_to_text(pr)})

                # --------------------------
                # tool__web_search: extract
                # --------------------------
                if parsed.full_name == "tool__web_search":
                    raw_result = trace.raw_result  # dict[str, object]
                    search_results = raw_result.get("results")

                    if isinstance(search_results, list):
                        lines: list[str] = ["Web search results (pick one URL if you need to fetch details):"]
                        for idx, item in enumerate(search_results[:5], 1):  # type: ignore
                            if not isinstance(item, dict):
                                continue
                            title = str(item.get("title", "") or "")  # type: ignore
                            url = str(item.get("url", "") or "")  # type: ignore
                            snippet = str(item.get("snippet", "") or "")  # type: ignore
                            lines.append(f"{idx}. {title}\n   {url}\n   {snippet}")
                        extra_msgs.append({"role": "user", "content": "\n".join(lines)})

                # --------------------------
                # tool__web_fetch: extract
                # --------------------------
                if parsed.full_name == "tool__web_fetch":
                    raw_result = trace.raw_result  # dict[str, object]

                    fetch_url = str(raw_result.get("url", "") or "")
                    status_code = raw_result.get("status_code", "")
                    content_type = str(raw_result.get("content_type", "") or "")
                    is_truncated = bool(raw_result.get("truncated", False))

                    fetch_text_obj = raw_result.get("text", "")
                    fetch_text = fetch_text_obj if isinstance(fetch_text_obj, str) else ""
                    preview = self._snip(fetch_text, 1200) if fetch_text else ""

                    lines = [
                        "Web fetch result (use this content to answer; if insufficient, fetch again with larger max_chars or another URL):",
                        f"- url: {fetch_url}",
                        f"- status_code: {status_code}",
                        f"- content_type: {content_type}",
                        f"- truncated: {is_truncated}",
                        "",
                        "Extracted text preview:",
                        preview,
                    ]
                    if is_truncated:
                        lines += [
                            "",
                            "Note: content was truncated. If you need more, call tool__web_fetch with a larger max_chars (up to 20000) or fetch a more specific URL section.",
                        ]

                    extra_msgs.append({"role": "user", "content": "\n".join(lines)})
            else:
                hint = TOOL_RETRY_HINTS.get(parsed.full_name, DEFAULT_RETRY_HINT)
                extra_msgs.append(
                    {
                        "role": "user",
                        "content": (f"[TOOL_ERROR] {parsed.full_name} failed.\nError: {trace.error}\n{hint}"),
                    }
                )
        return tool_msg, extra_msgs, trace

    async def run_tool_loop(
        self,
        *,
        tool_system_prompt: str,
        messages: list[dict[str, object]],
        available_tools: list[dict[str, object]],
        max_steps: int = 6,
        max_parallel_tools: int = 6,
        tool_output_as_user_prompt: bool = True,
        debug: bool = True,
    ) -> tuple[list[dict[str, object]], list[ToolTraceItem]]:
        """
        Tool Model：非流式
        - 协议正确：assistant(tool_calls) 后必须立刻补齐所有 tool messages（不能插 user/system）
        - 并行：同轮多个 tool_calls -> gather
        - 链式：补齐 tool messages 后，再追加 extra user messages 进入下一轮决策
        - 去重：同轮相同 (tool+args) 只真实调用一次，但每个 tool_call_id 都回填
        """

        tool_loop_messages = build_tool_context(
            tool_system_prompt=tool_system_prompt,  # 注意：这里用“短的 tool routing prompt”
            full_history=messages,
            state=self.state,
            cfg=self.tool_ctx_cfg,
        )
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

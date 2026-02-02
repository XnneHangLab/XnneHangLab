from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from loguru import logger

from lab.mcp import (
    DEFAULT_RETRY_HINT,
    TOOL_RETRY_HINTS,
    ConversationState,
    ImageRefResult,
    OpenAIMessage,
    ScreenShotResult,
    ToolCallLike,
    ToolMessage,
    ToolRegistry,
    ToolTraceItem,
    build_resolved_refs_msg,
    update_state_from_tool_trace,
    update_state_from_user_text,
)
from lab.mcp.util import dump_openai_msg, prompt_result_to_text

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
        self.blob_store: dict[str, dict[str, object]] = {}  # call_id -> {"mime":..., "b64":...}
        self.tool_ctx_cfg = tool_context_config

    def _snip(self, s: str, n: int = 1200) -> str:
        """截断字符串，保留前 n 个字符，加省略号"""
        ss = (s or "").strip()
        if len(ss) <= n:
            return ss
        return ss[:n] + f"\n...(preview truncated, {len(ss)} chars total)..."

    def _user_wants_reuse_screenshot(self, text: str, state: ConversationState) -> bool:
        t = text or ""
        return any(
            x in t
            for x in [
                "刚才那张截图",
                "那张截图",
                "上一个截图",
                "刚刚的截图",
                "上一张图",
                "刚才那张图",
                "上一张截图",
                "刚才那图片",
            ]
        )

    def _user_wants_new_screenshot(self, text: str) -> bool:
        t = text or ""
        return any(x in t for x in ["现在截图", "重新截图", "再截一张", "此刻截图", "再截图一次"])

    def _can_reuse_last_image(self, state: ConversationState) -> bool:
        refs = getattr(state, "refs", {})
        if not isinstance(refs, dict):
            return False
        ref = refs.get("last_image_ref")  # type: ignore
        return isinstance(ref, str) and ref in self.blob_store

    def _effective_tools_for_step(
        self,
        *,
        user_input: str,
        available_tools: list[dict[str, object]],
        state: ConversationState,
    ) -> list[dict[str, object]]:
        reuse = self._user_wants_reuse_screenshot(user_input, state) and not self._user_wants_new_screenshot(user_input)
        if reuse and self._can_reuse_last_image(state):
            logger.info("[TOOLS] reuse screenshot: disabling vision__screen_shot for this step")
            return [
                t
                for t in available_tools
                if t.get("function", {}).get("name") != "vision__screen_shot"  # type: ignore
            ]
        return available_tools

    async def _execute_tool_call(
        self,
        tool_call: ToolCallLike,
        *,
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
        args_dict = parsed.args_model.model_dump(exclude_none=True, mode="json")

        # 2) 调工具
        try:
            result_obj = await self.mcp.call_tool(full_name=full_name, args=args_dict)
            result_model = ToolRegistry.parse_result(full_name, result_obj)
            if isinstance(result_model, ScreenShotResult):
                b64 = result_model.image_b64
                self.blob_store[tool_call.id] = {"mime": "image/jpeg", "b64": b64}

                tool_msg = ToolMessage(
                    content=f"[screenshot captured] ref={tool_call.id} mime=image/jpeg b64_len={len(b64)}",
                    tool_call_id=tool_call.id,
                )

                # ✅ 关键：trace_item 直接吃 ImageRefResult，raw_result 统一建模
                trace = ToolRegistry.trace_item(
                    parsed,
                    ImageRefResult(image_ref=tool_call.id, mime="image/jpeg", b64_len=len(b64)),
                    ok=True,
                    error=None,
                )
            else:
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
        user_input: str,
        available_tools: list[dict[str, object]],
        max_steps: int = 6,
        max_parallel_tools: int = 6,
        debug: bool = True,
        state: ConversationState,
    ) -> tuple[list[dict[str, object]], list[ToolTraceItem]]:
        """
        Tool Model：非流式
        - 协议正确：assistant(tool_calls) 后必须立刻补齐所有 tool messages（不能插 user/system）
        - 并行：同轮多个 tool_calls -> gather
        - 链式：补齐 tool messages 后，再追加 extra user messages 进入下一轮决策
        - 去重：同轮相同 (tool+args) 只真实调用一次，但每个 tool_call_id 都回填
        """
        if debug:
            logger.info(f"[STATE] active_task={state.active_task} refs={state.refs} slots={list(state.slots.keys())}")
            logger.info(f"[STATE_JSON] {state.model_dump(exclude_none=True)}")
        # 初始 state 更新（last_user_text / last_url / last_file / choice）
        update_state_from_user_text(state, user_text=user_input)

        # 我们的 tool loop 只需要 system + user 这 2 条消息，在需要的时候才会追加上下文(根据 pinned state 和 匹配评分)
        tool_loop_messages: list[dict[str, object]] = [
            OpenAIMessage(role="system", content=tool_system_prompt).model_dump(exclude_none=True),
            OpenAIMessage(role="user", content=user_input).model_dump(exclude_none=True),
        ]

        tool_trace: list[ToolTraceItem] = []
        resolved_refs_msg = build_resolved_refs_msg(state, user_input)
        if resolved_refs_msg is not None:
            tool_loop_messages.append(resolved_refs_msg)

        cache: dict[str, tuple[str, ToolTraceItem, list[dict[str, object]]]] = {}

        def _sig(full_name: str, args_dict: dict[str, object]) -> str:
            return full_name + "::" + json.dumps(args_dict, ensure_ascii=False, sort_keys=True)

        for step in range(max_steps):
            tools_eff = self._effective_tools_for_step(
                user_input=user_input,
                available_tools=available_tools,
                state=state,
            )

            resp = await self.tool_llm.tool_completion(
                messages=tool_loop_messages,
                tools=tools_eff,  # ✅ 用 tools_eff
                tool_choice="auto",
                system=None,  # 你说 messages 已经包含 system，就别再传
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
            web_search_idx = next(
                (i for i, tc in enumerate(tool_calls_all) if tc.function.name == "tool__web_search"),
                None,
            )
            # 如果触发 Web Search，则本轮只执行它，不并行，独占一个 Step。
            # 这样做是为了更好地配合 Fetch，避免 Web Search Fetch 并行调用而让 Fetch 不完整。
            if web_search_idx is not None and len(tool_calls_all) > 1:
                tool_calls_exec = [tool_calls_all[web_search_idx]]
                tool_calls_skipped = [tc for j, tc in enumerate(tool_calls_all) if j != web_search_idx]
            else:
                tool_calls_exec = tool_calls_all[:max_parallel_tools]
                tool_calls_skipped = tool_calls_all[max_parallel_tools:]

            # 1) schedule real tool calls (dedupe by signature)
            tasks: list[asyncio.Task[tuple[ToolMessage, list[dict[str, object]], ToolTraceItem]]] = []
            planned: list[tuple[ToolCallLike, str]] = []

            for tool_call in tool_calls_exec:
                full_name = tool_call.function.name
                parsed = ToolRegistry.parse_args(full_name, tool_call.function.arguments)
                args_dict = parsed.args_model.model_dump(exclude_none=True, mode="json")
                sig = _sig(full_name, args_dict)
                planned.append((tool_call, sig))

                if sig in cache:
                    # 缓存命中：不真实调用，但后面仍要为这个 tool_call_id 回填 tool message
                    continue

                tasks.append(
                    asyncio.create_task(
                        self._execute_tool_call(
                            tool_call,
                        )
                    )
                )

            # 并行真实调用
            if tasks:
                results = await asyncio.gather(*tasks)
                # 写入缓存：用 signature 作为 key
                for tool_msg, extra_msgs, trace in results:
                    # 这里从 trace 反推 signature（或你可以让 _execute_tool_call 返回 sig）
                    full_name = f"{trace.server}__{trace.name}"
                    sig = _sig(full_name, trace.args)
                    cache[sig] = (tool_msg.content, trace, extra_msgs)
            # --- 2) 构造“本轮必须补齐的 tool messages”（对每个 tool_call_id 都要有）
            tool_msgs_to_append: list[dict[str, object]] = []
            extra_msgs_to_append: list[dict[str, object]] = []

            # 先处理执行集合（可能重复/缓存）
            for tool_call, sig in planned:
                if sig in cache:
                    cached_content, cached_trace, cached_extra = cache[sig]
                    tool_msgs_to_append.append(
                        ToolMessage(content=cached_content, tool_call_id=tool_call.id).model_dump(exclude_none=True)
                    )
                    # trace 只记录一次即可（避免重复膨胀）；你也可以加个 “reused=True”
                    if cached_trace not in tool_trace:
                        tool_trace.append(cached_trace)
                        update_state_from_tool_trace(state, cached_trace)

                    # extra 也只追加一次（否则会越滚越大）
                    if cached_extra:
                        for m in cached_extra:
                            if m not in extra_msgs_to_append:
                                extra_msgs_to_append.append(m)
                else:
                    # 理论上不会发生：没有进入 cache 说明真实调用没跑出来
                    tool_msgs_to_append.append(
                        ToolMessage(content="tool_error: missing result", tool_call_id=tool_call.id).model_dump(
                            exclude_none=True
                        )
                    )
            for tool_call in tool_calls_skipped:
                tool_msgs_to_append.append(
                    ToolMessage(
                        content="skipped_due_to_max_parallel_tools",
                        tool_call_id=tool_call.id,
                    ).model_dump(exclude_none=True)
                )

            # ✅ 协议关键：先追加所有 tool messages（连续）
            tool_loop_messages.extend(tool_msgs_to_append)

            # ✅ 再追加 extra user messages（用于链式决策）
            tool_loop_messages.extend(extra_msgs_to_append)

        return tool_loop_messages, tool_trace

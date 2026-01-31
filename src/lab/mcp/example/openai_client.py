from __future__ import annotations

import asyncio
import json
from pathlib import Path

from loguru import logger
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.mcp._typing import (
    ConversationState,
    ImageRefResult,
    OpenAIMessage,
    ScreenShotResult,
    ToolCallLike,
    ToolContextConfig,
    ToolMessage,
    ToolTraceItem,
)
from lab.mcp.context_policy import build_resolved_refs_msg
from lab.mcp.fastmcp_router import FastMcpRouter
from lab.mcp.state_updater import update_state_from_tool_trace, update_state_from_user_text
from lab.mcp.tool_registry import DEFAULT_RETRY_HINT, TOOL_RETRY_HINTS, ToolRegistry
from lab.mcp.util import call_with_short_retry, dump_openai_msg, prompt_result_to_text  # type: ignore


# =============================================================================
# 8) Agent：Tool loop（非流式）+ Chat（流式）
# =============================================================================
class Agent:
    """
    Agent 行为：
    - Tool Model（非流式）：决定是否调用工具；支持并行 tool_calls；支持链式多轮
    - Chat Model（流式）：使用 tool_trace 摘要产出最终回复（口语化交给它）
    """

    def __init__(self) -> None:
        self.config = load_settings_file("lab.toml", XnneHangLabSettings)

        tool_model = self.config.agent.tool_model
        chat_model = self.config.agent.chat_model
        tool_llm = getattr(self.config.agent.llm, tool_model.llm_provider)
        chat_llm = getattr(self.config.agent.llm, chat_model.llm_provider)
        self.state = ConversationState()
        self.tool_ctx_cfg = ToolContextConfig()  # 或从 lab.toml 加载
        self.tool_client = AsyncOpenAI(base_url=tool_llm.llm_base_url, api_key=tool_llm.llm_api_key)
        self.chat_client = AsyncOpenAI(base_url=chat_llm.llm_base_url, api_key=chat_llm.llm_api_key)

        self.tool_model_name = tool_model.llm_model_name
        self.chat_model_name = chat_model.llm_model_name
        self._load_system_prompt()
        self._blob_store: dict[str, dict[str, object]] = {}  # call_id -> {"mime":..., "b64":...}

        self.mcp = FastMcpRouter(prefix_delim="__")

    def _load_system_prompt(self) -> None:
        """
        加载角色系统提示词和工具系统提示词。
        """
        chat_system_path = Path("prompts") / "characters" / f"{self.config.agent.character_name}.txt"
        tool_system_path = Path("prompts") / "characters" / "tool_model.txt"
        chat_system_prompt = chat_system_path.read_text(encoding="utf-8") if chat_system_path.exists() else ""
        tool_system_prompt = tool_system_path.read_text(encoding="utf-8") if tool_system_path.exists() else ""

        self.chat_system_prompt = chat_system_prompt
        self.tool_system_prompt = tool_system_prompt

    def _snip(self, s: str, n: int = 1200) -> str:
        """截断字符串，保留前 n 个字符，加省略号"""
        ss = (s or "").strip()
        if len(ss) <= n:
            return ss
        return ss[:n] + f"\n...(preview truncated, {len(ss)} chars total)..."

    def _user_msg_with_image(self, text: str, *, b64: str, mime: str = "image/jpeg") -> dict[str, object]:
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }

    def _first_image_ref(self, tool_trace: list[ToolTraceItem]) -> str | None:
        """
        从 tool_trace 中提取第一个 image_ref。
        试图 match 这样一个对象：
        trace.raw_result = {
            "image_ref": tool_call.id,
            "mime": "image/jpeg",
            "b64_len": len(b64),
        }
        局限是：
        仅仅支持单图片场景，且 image_ref 必须在 raw_result 里。
        不过鉴于 openai 一次传入多个 image_url 的识别率直线下降（以前用 llm 做电池缺陷识别的经验），这里仅支持单图片场景，比如：
        调用 screen shoot，或者调用摄像机等工具，来获取图片，一般更建议多次调用然后每次对单张图片进行分析而不是一次调用获取多张图片。
        """
        for t in tool_trace:
            raw = t.raw_result or {}
            if isinstance(raw, dict):  # type: ignore
                if raw.get("kind") == "image_ref":
                    v = raw.get("image_ref")
                    if isinstance(v, str) and v:
                        return v
                # 兼容旧格式（如果你历史里存在）
                v2 = raw.get("image_ref")
                if isinstance(v2, str) and v2:
                    return v2
        return None

    async def connect_mcp_servers(self) -> None:
        """
        连接你已启动的 FastMCP servers（你配置里 path="/"）。
        """
        await self.mcp.connect(name="timeemi", url="http://127.0.0.1:4200/")
        await self.mcp.connect(name="vision", url="http://127.0.0.1:4201/")
        await self.mcp.connect(name="tool", url="http://127.0.0.1:4202/")

    async def close(self) -> None:
        await self.mcp.close()

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
        args_dict = parsed.args_model.model_dump(exclude_none=True, mode="json")

        # 2) 调工具
        try:
            result_obj = await self.mcp.call_tool(full_name=full_name, args=args_dict)
            result_model = ToolRegistry.parse_result(full_name, result_obj)

            if isinstance(result_model, ScreenShotResult):
                b64 = result_model.image_b64
                self._blob_store[tool_call.id] = {"mime": "image/jpeg", "b64": b64}

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
        user_input: str,
        available_tools: list[dict[str, object]],
        max_steps: int = 6,
        max_parallel_tools: int = 6,
        debug: bool = True,
    ) -> tuple[list[dict[str, object]], list[ToolTraceItem]]:
        """
        Tool Model：非流式
        - 协议正确：assistant(tool_calls) 后必须立刻补齐所有 tool messages（不能插 user/system）
        - 并行：同轮多个 tool_calls -> gather
        - 链式：补齐 tool messages 后，再追加 extra user messages 进入下一轮决策
        - 去重：同轮相同 (tool+args) 只真实调用一次，但每个 tool_call_id 都回填
        """
        if debug:
            logger.info(
                f"[STATE] active_task={self.state.active_task} refs={self.state.refs} slots={list(self.state.slots.keys())}"
            )
            logger.info(f"[STATE_JSON] {self.state.model_dump(exclude_none=True)}")

        # 初始 state 更新（last_user_text / last_url / last_file / choice）
        update_state_from_user_text(self.state, user_input)
        tool_loop_messages: list[dict[str, object]] = [
            OpenAIMessage(role="system", content=self.tool_system_prompt).model_dump(exclude_none=True),
            OpenAIMessage(role="user", content=user_input).model_dump(exclude_none=True),
        ]
        tool_trace: list[ToolTraceItem] = []
        resolved_refs_msg = build_resolved_refs_msg(self.state, user_input)
        if resolved_refs_msg is not None:
            tool_loop_messages.append(resolved_refs_msg)

        # 跨 step 的缓存：避免重复真实调用（可选但很省）
        cache: dict[str, tuple[str, ToolTraceItem, list[dict[str, object]]]] = {}

        def _sig(full_name: str, args_dict: dict[str, object]) -> str:
            return full_name + "::" + json.dumps(args_dict, ensure_ascii=False, sort_keys=True, default=str)

        for step in range(max_steps):
            resp = await call_with_short_retry(  # type: ignore
                lambda: self.tool_client.chat.completions.create(  # type: ignore
                    model=self.tool_model_name,
                    messages=tool_loop_messages,  # type: ignore
                    tools=available_tools,  # type: ignore
                    tool_choice="auto",
                    stream=False,
                ),
                max_retries=2,
            )

            assistant_msg = resp.choices[0].message  # type: ignore
            tool_loop_messages.append(dump_openai_msg(assistant_msg))  # type: ignore

            tool_calls = getattr(assistant_msg, "tool_calls", None)  # type: ignore
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

            # --- 1) 先为“要执行的 tool_calls”准备任务（并行 + 去重/缓存）
            tasks: list[asyncio.Task[tuple[ToolMessage, list[dict[str, object]], ToolTraceItem]]] = []
            planned: list[tuple[ToolCallLike, str]] = []  # (tool_call, signature)

            for tc in tool_calls_exec:
                full_name = tc.function.name
                parsed = ToolRegistry.parse_args(full_name, tc.function.arguments)
                args_dict = parsed.args_model.model_dump(exclude_none=True, mode="json")
                sig = _sig(full_name, args_dict)
                planned.append((tc, sig))

                if sig in cache:
                    # 缓存命中：不真实调用，但后面仍要为这个 tool_call_id 回填 tool message
                    continue

                # 真实调用
                tasks.append(asyncio.create_task(self._execute_tool_call(tc, user_input=user_input)))

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
            for tc, sig in planned:
                if sig in cache:
                    cached_content, cached_trace, cached_extra = cache[sig]
                    tool_msgs_to_append.append(
                        ToolMessage(content=cached_content, tool_call_id=tc.id).model_dump(exclude_none=True)
                    )
                    # trace 只记录一次即可（避免重复膨胀）；你也可以加个 “reused=True”
                    if cached_trace not in tool_trace:
                        tool_trace.append(cached_trace)
                        update_state_from_tool_trace(self.state, cached_trace)

                    # extra 也只追加一次（否则会越滚越大）
                    if cached_extra:
                        for m in cached_extra:
                            if m not in extra_msgs_to_append:
                                extra_msgs_to_append.append(m)
                else:
                    # 理论上不会发生：没有进入 cache 说明真实调用没跑出来
                    tool_msgs_to_append.append(
                        ToolMessage(content="tool_error: missing result", tool_call_id=tc.id).model_dump(
                            exclude_none=True
                        )
                    )

            # 再处理被截断的 tool_calls：也必须回填 tool message，否则必 400
            for tc in tool_calls_skipped:
                tool_msgs_to_append.append(
                    ToolMessage(
                        content="skipped_due_to_max_parallel_tools",
                        tool_call_id=tc.id,
                    ).model_dump(exclude_none=True)
                )

            # ✅ 协议关键：先追加所有 tool messages（连续）
            tool_loop_messages.extend(tool_msgs_to_append)

            # ✅ 再追加 extra user messages（用于链式决策）
            tool_loop_messages.extend(extra_msgs_to_append)

        return tool_loop_messages, tool_trace

    async def stream_chat_answer(
        self,
        *,
        user_input: str,
        tool_trace: list[ToolTraceItem],
    ):
        """
        Chat Model：流式输出最终回复（不做工具调用）。

        关键点：
        - 口语化/TTS 友好由 Chat Model 完成
        - 我们只提供结构化 trace，避免在 client 侧硬编码口语化逻辑
        """
        img_ref = None
        # ✅ 优先从 state 拿（更稳：即使 tool_trace 被裁剪/压缩也不影响）
        if isinstance(getattr(self, "state", None), object):
            refs = getattr(self.state, "refs", {})
            if isinstance(refs, dict):
                v = refs.get("last_image_ref")  # type: ignore
                if isinstance(v, str):
                    img_ref = v

        img_ref = img_ref or self._first_image_ref(tool_trace)

        trace_dump = [t.model_dump(exclude_none=True, mode="json") for t in tool_trace]
        tool_summary = json.dumps(trace_dump, ensure_ascii=False, indent=2, default=str) if trace_dump else "[]"
        messages = [
            OpenAIMessage(role="system", content=self.chat_system_prompt).model_dump(exclude_none=True),
            OpenAIMessage(
                role="user",
                content=(
                    "这是通过工具拿到结构化结果（JSON）。"
                    "请基于这些结果用自然口语回答，并让输出适合 TTS 朗读（避免太“机器格式”）。\n\n"
                    f"工具结果摘要：\n{tool_summary}"
                ),
            ).model_dump(exclude_none=True),
        ]
        if img_ref and img_ref in self._blob_store:
            blob = self._blob_store[img_ref]  # 由 tool_trace.id 反推 img_ref
            b64 = str(blob["b64"])
            mime = str(blob.get("mime", "image/jpeg"))

            # ⚠️ 这里请用“支持 vision 的 chat_model”
            # 比如你可以在 config 里专门配一个 chat_vision_model
            messages.append(
                self._user_msg_with_image(user_input, b64=b64, mime=mime),
            )
        else:
            messages.append(
                OpenAIMessage(role="user", content=user_input).model_dump(exclude_none=True),
            )
        stream = await call_with_short_retry(  # type: ignore
            lambda: self.chat_client.chat.completions.create(  # type: ignore
                model=self.chat_model_name,  # type: ignore
                messages=messages,  # type: ignore
                stream=True,
            ),
            max_retries=2,
        )

        async for chunk in stream:  # type: ignore
            delta = chunk.choices[0].delta  # type: ignore
            content = getattr(delta, "content", None)  # type: ignore
            if content:
                yield content

    async def chat_stream(self, user_input: str, *, debug: bool = True):
        available_tools = await self.mcp.list_tools_openai_schema()

        _, tool_trace = await self.run_tool_loop(
            user_input=user_input,
            available_tools=available_tools,
            debug=debug,
        )

        if debug:
            logger.info("[ToolTrace]")
            for t in tool_trace:
                logger.info(f"  - {t.server}::{t.name} args={t.args} ok={t.ok} result={t.raw_result} error={t.error}")

        async for tok in self.stream_chat_answer(
            user_input=user_input, tool_trace=tool_trace
        ):
            yield tok


# =============================================================================
# 9) main：你的 5 个示例
# =============================================================================
async def main():
    agent = Agent()
    try:
        await agent.connect_mcp_servers()

        async def run(q: str):
            print(f"\n\n=== Q: {q} ===")
            try:
                async for tok in agent.chat_stream(q, debug=True):
                    print(tok, end="", flush=True)
                print("\n=== END ===")
            except (APIConnectionError, APIError, RateLimitError) as e:
                print(f"\n[LLM error] {e}")

        async def run_dialog(turns: list[str]):
            for q in turns:
                print(f"\n\n=== Q: {q} ===")
                async for tok in agent.chat_stream(q, debug=True):
                    print(tok, end="", flush=True)
                print("\n=== END ===")

        await run("我晚上九点就后就该去打游戏了，现在几点？")
        await run("现在几点？现在几点你就帮我随便 roll 几个点数")
        await run("你今天真可爱")
        await run("https://xnnehang.top/posts/default/chill_ai_chat_mod, 这个博客讲啥了？")
        await run("https://alma.now/docs/guide/, 帮我用中文解释下这个网页的内容。")
        await run("./README.md 这个文件里面讲了什么内容？")
        await run("帮我搜索一下XnneHangLab，告诉我它是做什么的？")
        await run("你能看到我现在的桌面环境吗？描述一下。")
        await run_dialog(
            [
                "https://alma.now/docs/guide/ , 用中文解释下这页讲什么",
                "把上一个链接再总结一遍，换成更口语一点",
            ]
        )
        await run_dialog(
            [
                "你能看到我现在的桌面环境吗？描述一下。",
                "刚才那张截图里，最显眼的窗口是什么？用一句话说",
            ]
        )

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())

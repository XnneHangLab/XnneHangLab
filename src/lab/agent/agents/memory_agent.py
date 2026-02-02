from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

from lab.agent.agents.agent_interface import AgentInterface
from lab.agent.input_types import BatchInput, TextSource
from lab.agent.mcp_tool_loop import McpToolLoopRunner
from lab.agent.transformers import actions_extractor, display_processor, sentence_divider, tts_filter
from lab.chat_history_manager import get_history
from lab.mcp import ConversationState, FastMcpRouter
from lab.mcp.util import call_with_short_retry  # type: ignore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from lab.agent.output_types import AudioOutput, DisplayText, SentenceOutput
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.config_manager.config import XnneHangLabSettings
    from lab.config_manager.vtuber import TTSPreprocessorConfig
    from lab.live2d_model import Live2dModel
    from lab.mcp import ToolTraceItem


class MemoryAgent(AgentInterface):
    """A single agent that can run in two modes:

    - enable_tool=False (default): Basic memory chat (streaming)
    - enable_tool=True: MCP tool loop (non-stream) + final chat streaming

    Final output ALWAYS goes through the transformer pipeline for TTS (same as BasicMemoryAgent).
    """

    def __init__(
        self,
        *,
        lab_settings: XnneHangLabSettings,
        chat_llm: AsyncLLM,
        tool_llm: AsyncLLM,
        vision_llm: AsyncLLM,
        chat_system_prompt: str,
        tool_system_prompt: str,
        vision_system_prompt: str,
        live2d_model: Live2dModel,
        tts_preprocessor_config: TTSPreprocessorConfig,
        enable_tool: bool = False,
        mcp: FastMcpRouter | None = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
        interrupt_method: Literal["system", "user"] = "user",
    ) -> None:
        super().__init__()
        self.lab_settings = lab_settings
        self.state = ConversationState()  # 这是动态状态，不是配置
        self.tool_ctx_cfg = self.lab_settings.mcp.tool_context  # 或从 lab.toml 加载，静态配置
        self._memory: list[dict[str, str]] = []
        # ✅ LLM 接口
        self.chat_llm = chat_llm
        self.tool_llm = tool_llm
        self.vision_llm = vision_llm
        self.chat_system_prompt = chat_system_prompt
        self.tool_system_prompt = tool_system_prompt
        self.vision_system_prompt = vision_system_prompt
        # ✅ 新增：能力开关
        self.chat_supports_vision = self.lab_settings.agent.chat_model.support_vision

        # MCP 相关
        self.enable_tool = enable_tool
        self.mcp = mcp or FastMcpRouter(prefix_delim="__")
        self.tool_loop = McpToolLoopRunner(
            tool_llm=self.tool_llm, mcp=self.mcp, tool_context_config=lab_settings.mcp.tool_context
        )

        self._live2d_model = live2d_model

        # tts preprocessor config
        self.tts_preprocessor_config = tts_preprocessor_config
        self.faster_first_response = faster_first_response
        self.segment_method = segment_method
        self.interrupt_method = interrupt_method
        self.interrupt_handled = False

        # bind chat pipeline
        self.chat = self._chat_function_factory(self._stream_chat_tokens)  # type: ignore[method-assign]

        logger.info(f"MemoryAgent initialized. enable_tool={self.enable_tool}")

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

    async def _get_vision_summary(
        self,
        *,
        user_input: str,
        img_ref: str,
        b64: str,
        mime: str,
    ) -> str:
        # ✅ 缓存：同一张图别反复总结
        cache_key = f"vision_summary::{img_ref}"
        cached = self.state.slots.get(cache_key)
        if isinstance(cached, str) and cached.strip():
            return cached

        if not self.vision_llm:
            return ""

        # 视觉模型只做“抽取/结构化摘要”，不要写长文，不要角色扮演
        vision_system = self.vision_system_prompt

        # ✅ 这里要把图发给 vision_model（它支持 vision）
        msgs: list[dict[str, object]] = [
            {"role": "system", "content": vision_system},
            self._user_msg_with_image(
                f"用户问题：{user_input}\n请抽取与问题最相关的信息。",
                b64=b64,
                mime=mime,
            ),
        ]

        text_summary = await self.vision_llm.vision_completion_once(  # type: ignore[attr-defined]
            messages=msgs,
            system=vision_system,
        )
        if text_summary:
            # cache it
            self.state.slots[cache_key] = text_summary
            logger.info(f"[VISION] cached vision summary for img_ref={img_ref}: {self._snip(text_summary)}")
        return text_summary

    # ---------------------------------------------------------------------
    # MCP lifecycle
    # ---------------------------------------------------------------------
    async def connect_mcp_servers(self, servers: list[tuple[str, str]] | None = None) -> None:
        if servers:
            for name, url in servers:
                await self.mcp.connect(name=name, url=url)
            return

        for name, s in [
            ("timeemi", self.lab_settings.mcp.servers.timeemi),
            ("vision", self.lab_settings.mcp.servers.vision),
            ("tool", self.lab_settings.mcp.servers.tool),
        ]:
            url = f"{s.transport}://{s.host}:{s.port}{s.path}"  # http://127.0.0.1:4200/ 我们只考虑 http, stdio 无法在 uvicorn 中运行.
            await self.mcp.connect(name=name, url=url)

    async def close(self) -> None:
        await self.mcp.close()

    # ---------------------------------------------------------------------
    # Basic memory ops
    # ---------------------------------------------------------------------

    def _add_message(
        self,
        message: str | list[dict[str, Any]],
        role: str,
        display_text: DisplayText | None = None,
    ) -> None:
        if isinstance(message, list):
            text_content = ""
            for item in message:
                if item.get("type") == "text":
                    text_content += str(item.get("text", ""))
        else:
            text_content = message

        if role == "assistant" and display_text is not None:
            content = display_text.text
        else:
            content = text_content

        self._memory.append({"role": role, "content": content})

    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """Load user/assistant messages from chat history.

        Note: we DO NOT inject system prompt into memory; system is passed separately to the LLM.
        """
        messages = get_history(conf_uid, history_uid)
        self._memory = []
        for msg in messages:
            self._memory.append(
                {
                    "role": "user"
                    if msg["role"] == "human"
                    else "assistant",  # bug: 这里可能会有 tool call 的 tool message, 但是暂时也就当成 assistant 处理, 具体得看怎么写的 history
                    "content": msg["content"],
                }
            )

    def handle_interrupt(self, heard_response: str) -> None:
        if self.interrupt_handled:
            return
        self.interrupt_handled = True

        if self._memory and self._memory[-1]["role"] == "assistant":
            self._memory[-1]["content"] = heard_response + "..."
        elif heard_response:
            self._memory.append({"role": "assistant", "content": heard_response + "..."})

        self._memory.append(
            {
                "role": "system" if self.interrupt_method == "system" else "user",
                "content": "[interrupted by user]",
            }
        )

    def reset_interrupt(self) -> None:
        self._interrupt_handled = False

    # ---------------------------------------------------------------------
    # Prompt / messages
    # ---------------------------------------------------------------------
    def _to_text_prompt(self, input_data: BatchInput) -> str:
        parts: list[str] = []
        for text_data in input_data.texts:
            if text_data.source == TextSource.INPUT:
                parts.append(text_data.content)
            elif text_data.source == TextSource.CLIPBOARD:
                parts.append(f"[Clipboard content: {text_data.content}]")
        return "\n".join(parts)

    # ---------------------------------------------------------------------
    # Core streaming (with optional MCP tool loop)
    # ---------------------------------------------------------------------
    async def _stream_chat_tokens(self, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        if not self.enable_tool:
            self._add_message(messages[-1]["content"], "user")  # 直接添加 user message 到 memory 中
            async for tok in self.chat_llm.chat_completion(  # type: ignore[attr-defined]
                messages,  # type: ignore[arg-type]
                self.chat_system_prompt,
                stream_=True,
            ):
                yield tok
            return

        # tool mode

        available_tools = await self.mcp.list_tools_openai_schema()
        # 如果 user input 的来源是 _memory 且是由 chat_func 调用的，那么最后一条消息一定是 user,而这里防的是其他情况
        user_input_content: list[dict[str, Any]] | str = (
            messages[-1]["content"]
            if messages[-1]["role"] == "user"
            else ValueError(f"last message must be user,but got {messages[-1]['role']}")
        )  # type: ignore[assignment]
        messages = messages[
            :-1
        ]  # remove last user message for now , 因为我们会在 tool loop 中添加 tool summary, 以 role=user 的身份添加到 memory 中
        user_input_text = ""
        if isinstance(user_input_content, list):
            for item in user_input_content:
                if item.get("type") == "text":
                    user_input_text += str(item.get("text", ""))
        # 我们暂时没有 tool call 需要图片输入的场景，有的话再做支持
        _, tool_trace = await self.tool_loop.run_tool_loop(
            tool_system_prompt=self.tool_system_prompt,
            available_tools=available_tools,
            debug=False,
            state=self.state,
            user_input=user_input_text,
        )

        tool_summary = json.dumps(
            [t.model_dump(exclude_none=True, mode="json") for t in tool_trace],  # type: ignore[attr-defined]
            ensure_ascii=False,
            indent=2,
        )

        tools_summary_str = f"工具结果摘要：\n{tool_summary}"
        messages.append({"role": "user", "content": tools_summary_str})

        self._add_message(tools_summary_str, "user")

        img_ref = None
        # ✅ 优先从 state 拿（更稳：即使 tool_trace 被裁剪/压缩也不影响）
        if isinstance(getattr(self, "state", None), object):
            refs = getattr(self.state, "refs", {})
            if isinstance(refs, dict):
                v = refs.get("last_image_ref")  # type: ignore
                if isinstance(v, str):
                    img_ref = v

        img_ref = img_ref or self._first_image_ref(tool_trace)
        if img_ref and img_ref in self.tool_loop.blob_store:
            blob = self.tool_loop.blob_store[img_ref]
            b64 = str(blob["b64"])
            mime = str(blob.get("mime", "image/jpeg"))
            if self.chat_supports_vision:
                # ✅ 直接让 chat_model 看图（一次调用，最简单）
                messages.append(self._user_msg_with_image(user_input_text, b64=b64, mime=mime))
                self._add_message(user_input_text, "user")  # history 中并不存 base64 图像数据
            else:
                # ✅ chat text-only：走 vision fallback summary
                vision_summary = await self._get_vision_summary(
                    user_input=user_input_text, img_ref=img_ref, b64=b64, mime=mime
                )
                if vision_summary:
                    logger.debug(f"[VISION] obtained vision summary for chat: {self._snip(vision_summary)}")
                    vision_summary_prompt = (
                        "以下是视觉模型对图片的结构化摘要（JSON）。请把它当作“图片内容的真实信息来源”，结合工具结果与用户问题作答。"
                        f"VISION_SUMMARY:{vision_summary}"
                        f"用户问题：{user_input_text}"
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": vision_summary_prompt,
                        }
                    )
                    self._add_message(vision_summary_prompt, "user")
                else:
                    # ✅ 没有 vision_model 可用：只能不看图
                    logger.debug(f"[VISION] no vision summary for chat: {self._snip(user_input_text)}")
                    vision_summary_prompt = (
                        "注意：当前 chat_model 不支持图像输入，且未配置可用的 vision_model，"
                        "你应该先告诉用户你无法读取图片内容，不要胡编乱造。\n\n"
                        f"用户问题：{user_input_text}"
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": vision_summary_prompt,
                        }
                    )
                    self._add_message(vision_summary_prompt, "user")
        else:
            messages.append({"role": "user", "content": user_input_text})
            self._add_message(user_input_text, "user")

        async for tok in self.chat_llm.chat_completion(  # type: ignore[attr-defined]
            messages,  # type: ignore[arg-type]
            system=self.chat_system_prompt,
            stream_=True,
        ):
            yield tok

    # ---------------------------------------------------------------------
    # Transformer pipeline binding (kept!)
    # ---------------------------------------------------------------------
    def _chat_function_factory(
        self,
        chat_func: Callable[[list[dict[str, object]]], AsyncIterator[str]],
    ) -> Callable[..., AsyncIterator[SentenceOutput | AudioOutput]]:
        """Pipeline:
        LLM tokens -> sentence_divider -> actions_extractor -> display_processor -> tts_filter
        """

        @tts_filter(self.tts_preprocessor_config)
        @display_processor()
        @actions_extractor(self._live2d_model)
        @sentence_divider(
            faster_first_response=self.faster_first_response,
            segment_method=self.segment_method,
            valid_tags=["think"],
        )
        async def chat_with_memory(input_data: BatchInput) -> AsyncIterator[str | AudioOutput]:
            user_prompt = self._to_text_prompt(input_data)

            # build messages WITHOUT system (system is passed separately)
            messages: list[dict[str, object]] = [*self._memory, {"role": "user", "content": user_prompt}]  # type: ignore[arg-type]

            token_stream = chat_func(messages)
            complete_response = ""

            async for token in token_stream:
                yield token
                complete_response += token

            # store assistant message
            self._add_message(complete_response, "assistant")

        return chat_with_memory

    async def chat(self, input_data: BatchInput):  # type: ignore[override]
        return self.chat(input_data)  # type: ignore[return-value]

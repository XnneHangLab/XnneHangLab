from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Literal

from loguru import logger

from lab.agent.agents.agent_interface import AgentInterface
from lab.agent.input_types import BatchInput, TextSource
from lab.agent.mcp_tool_loop import McpToolLoopRunner
from lab.agent.transformers import actions_extractor, display_processor, sentence_divider, tts_filter
from lab.chat_history_manager import get_history, store_message
from lab.mcp import ContentPart, ConversationState, FastMcpRouter, ImagePart, OpenAIMessage, TextPart
from lab.mcp._typing import ImageURL

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
        self._memory: list[OpenAIMessage] = []
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

        self.history_uid: str | None = None
        self.conf_uid: str | None = None

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

    def _user_msg_with_image_from_screen_shoot(self, text: str, *, b64: str, mime: str = "image/jpeg") -> OpenAIMessage:
        content_parts: list[ContentPart] = [
            TextPart(type="text", text=text),
            ImagePart(type="image_url", image_url=ImageURL(url=f"data:{mime};base64,{b64}")),
        ]

        return OpenAIMessage(
            role="user",
            content=content_parts,
        )

    def _user_msg_with_image_from_upload(self, text: str, data: str) -> OpenAIMessage:
        """
        data like: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA4QAAAKeCAYAAADAeD/Mw...
        [{'source': 'upload', 'data': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA4QAAAKeCAYAAADAeD/Mw...', 'mime': 'image/png'}]
        """
        content_parts: list[ContentPart] = [
            TextPart(type="text", text=text),
            ImagePart(type="image_url", image_url=ImageURL(url=data)),
        ]

        return OpenAIMessage(
            role="user",
            content=content_parts,
        )

    def _user_msg_with_images(self, text: str, *, images: list[tuple[str, str]]) -> OpenAIMessage:
        """
        images: [(b64, mime), ...]
        """
        parts: list[ContentPart] = [TextPart(type="text", text=text)]
        for b64, mime in images:
            parts.append(ImagePart(type="image_url", image_url=ImageURL(url=f"data:{mime};base64,{b64}")))
        return OpenAIMessage(role="user", content=parts)

    def _extract_text_and_first_data_image(self, msg: OpenAIMessage) -> tuple[str, str | None, str | None]:
        """
        从 OpenAIMessage 中抽取：
        - text：拼起来的 text parts
        - b64/mime：只取第一张 data-url base64 图
        """
        if isinstance(msg.content, str):
            return msg.content, None, None

        text = ""
        b64: str | None = None
        mime: str | None = None

        if not msg.content:
            return "", None, None

        for part in msg.content:
            if part.type == "text":
                text += str(part.text)
            elif part.type == "image_url":
                url = getattr(part.image_url, "url", "")
                if isinstance(url, str) and url.startswith("data:") and ";base64," in url:
                    head, _, b64data = url.partition(";base64,")
                    mime = head[5:] or "image/jpeg"
                    b64 = b64data
                    break

        return text, b64, mime

    def _img_ref_from_b64(self, b64: str, mime: str) -> str:
        """
        给“用户上传图”生成稳定 cache key，避免重复 summary。
        不 hash 全量 b64（太大），用长度 + 前缀采样。
        """
        h = hashlib.sha1()
        h.update(mime.encode("utf-8"))
        h.update(str(len(b64)).encode("utf-8"))
        h.update(b64[:8192].encode("utf-8"))
        return h.hexdigest()

    def _build_prompt_with_image_summaries(
        self,
        *,
        user_input_text: str,
        tools_summary_str: str,
        tool_image_summary: str | None,
        user_image_summary: str | None,
    ) -> str:
        tool_block = (
            f"以下是视觉模型对 Tool Call 回调图片（调用工具截图）的图片内容信息：\n{tool_image_summary}"
            if tool_image_summary
            else "本次并未回调图片。"
        )
        user_block = (
            f"以下是视觉模型对用户上传图片内容的信息：\n{user_image_summary}"
            if user_image_summary
            else "本次用户没有上传图片。"
        )

        blocks = [
            f"[Task / User Prompt]\n{user_input_text}",
            f"[Tool Call Summary]\n{tools_summary_str}",
            f"[Tool Call Image Summary]\n{tool_block}",
            f"[User Upload Image Summary]\n{user_block}",
        ]
        return "\n\n###\n\n".join(blocks)

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
        msgs: list[OpenAIMessage] = [
            OpenAIMessage(role="system", content=vision_system),
            self._user_msg_with_image_from_screen_shoot(
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
        message: OpenAIMessage,
        display_text: DisplayText | None = None,
    ) -> None:
        if isinstance(message.content, str):
            text_content = message.content
        else:
            text_content = ""
            if message.content is None:
                return
            for item in message.content:
                if item.type == "text":
                    text_content += str(item.text)

        if message.role == "assistant" and display_text is not None:
            content = display_text.text
        else:
            content = text_content

        self._memory.append(OpenAIMessage(role=message.role, content=content))
        if self.history_uid and self.conf_uid:
            store_message(
                conf_uid=self.conf_uid,
                history_uid=self.history_uid,
                role=message.role,
                content=content,
            )

    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """Load user/assistant messages from chat history.

        Note: we DO NOT inject system prompt into memory; system is passed separately to the LLM.
        """
        messages = get_history(conf_uid, history_uid)
        self.conf_uid = conf_uid
        self.history_uid = history_uid
        self._memory = []
        for msg in messages:
            self._memory.append(
                OpenAIMessage(
                    role="user" if msg["role"] == "human" or msg["role"] == "user" else "assistant",
                    content=msg["content"],
                )
            )

    def handle_interrupt(self, heard_response: str) -> None:
        if self.interrupt_handled:
            return
        self.interrupt_handled = True

        if self._memory and self._memory[-1].role == "assistant":
            self._memory[-1].content = heard_response + "..."
        elif heard_response:
            self._memory.append(OpenAIMessage(role="assistant", content=heard_response + "..."))

        self._memory.append(
            OpenAIMessage(
                role="system" if self.interrupt_method == "system" else "user",
                content="[interrupted by user]",
            )
        )

    def reset_interrupt(self) -> None:
        self._interrupt_handled = False

    # ------------------------------
    # BatchInput -> user message (keep as-is)
    # ------------------------------
    def _to_text_prompt(self, input_data: BatchInput) -> str:
        parts: list[str] = []
        for text_data in input_data.texts:
            if text_data.source == TextSource.INPUT:
                parts.append(text_data.content)
            elif text_data.source == TextSource.CLIPBOARD:
                parts.append(f"[Clipboard content: {text_data.content}]")
        return "\n".join(parts)

    def _build_user_message_from_batch(self, input_data: BatchInput) -> OpenAIMessage:
        user_prompt = self._to_text_prompt(input_data)
        # 这里不做 vision 分流，只负责“把用户上传图挂上去”
        if input_data.images:
            img0 = input_data.images[0]
            return self._user_msg_with_image_from_upload(user_prompt, data=img0.data)

        return OpenAIMessage(role="user", content=user_prompt)

    # ---------------------------------------------------------------------
    # Core streaming (with optional MCP tool loop)
    # ---------------------------------------------------------------------
    async def _stream_chat_tokens(self, messages: list[OpenAIMessage]) -> AsyncIterator[str]:
        assert messages and messages[-1].role == "user", "last message must be user"

        # 先从最后一条 user message 里把“用户上传图”解析出来（tool 模式和非 tool 模式都用得到）
        user_input_text, user_up_b64, user_up_mime = self._extract_text_and_first_data_image(messages[-1])
        # ------------------------------
        # No-tool mode
        # ------------------------------
        if not self.enable_tool:
            # 如果 chat 不支持 vision，但用户上传了图，则走 vision_summary fallback（避免把 image_url 发给不支持的模型）
            if (not self.chat_supports_vision) and user_up_b64:
                if self.vision_llm:
                    user_ref = self._img_ref_from_b64(user_up_b64, user_up_mime or "image/jpeg")
                    user_sum = await self._get_vision_summary(
                        user_input=user_input_text,
                        img_ref=user_ref,
                        b64=user_up_b64,
                        mime=user_up_mime or "image/jpeg",
                    )
                    prompt = "\n\n###\n\n".join(
                        [
                            f"[Task / User Prompt]\n{user_input_text}",
                            f"[User Upload Image Summary]\n以下是视觉模型对用户上传图片内容的信息：\n{user_sum}",
                        ]
                    )
                else:
                    prompt = (
                        "注意：当前 chat_model 不支持图像输入，且未配置可用的 vision_model，无法读取图片内容。\n\n"
                        f"{user_input_text}"
                    )

                # 发给模型纯文本；history 也存纯文本
                send_msg = OpenAIMessage(role="user", content=prompt)
                mem_msg = OpenAIMessage(role="user", content=prompt)
                messages = [*messages[:-1], send_msg]
                self._add_message(mem_msg)
            else:
                # chat 支持 vision 或者用户没图：直接把原消息发给模型
                # 但 history 仍然只存纯文本（安全）
                send_msg = messages[-1]
                mem_msg = OpenAIMessage(role="user", content=user_input_text)
                messages = [*messages[:-1], send_msg]
                self._add_message(mem_msg)

            async for tok in self.chat_llm.chat_completion(  # type: ignore[attr-defined]
                messages,  # type: ignore[arg-type]
                self.chat_system_prompt,
                stream_=True,
            ):
                yield tok
            return

        # ------------------------------
        # Tool mode
        # ------------------------------

        available_tools = await self.mcp.list_tools_openai_schema()
        # tool loop 只吃 text（不把 data-url base64 传进去）
        messages_wo_user = messages[:-1]

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
        tools_summary_str = f"[Tool Call Summary]:\n{tool_summary}"

        # ---- 取 tool 回调图片（截图）----
        img_ref = None
        refs = getattr(self.state, "refs", {})
        if isinstance(refs, dict):
            v = refs.get("last_image_ref")  # type: ignore
            if isinstance(v, str):
                img_ref = v
        img_ref = img_ref or self._first_image_ref(tool_trace)

        tool_b64 = None
        tool_mime = None
        if img_ref and img_ref in self.tool_loop.blob_store:
            blob = self.tool_loop.blob_store[img_ref]
            tool_b64 = str(blob["b64"])
            tool_mime = str(blob.get("mime", "image/jpeg"))

        # prompt 主体（四段里前两段用这个做基础）----
        base_prompt = "\n\n###\n\n".join(
            [
                f"[Task / User Prompt]\n{user_input_text}",
                f"[Tool Call Summary]\n{tools_summary_str}",
            ]
        )

        # ==============================
        # A) chat_model 支持 vision：把两张图一起打包送进去
        # ==============================
        if self.chat_supports_vision:
            images_to_send: list[tuple[str, str]] = []
            if tool_b64:
                images_to_send.append((tool_b64, tool_mime or "image/jpeg"))
            if user_up_b64:
                images_to_send.append((user_up_b64, user_up_mime or "image/jpeg"))

            if images_to_send:
                send_msg = self._user_msg_with_images(base_prompt, images=images_to_send)
                mem_msg = OpenAIMessage(role="user", content=base_prompt)  # ✅ history 不存 base64
                final_messages = [*messages_wo_user, send_msg]
                self._add_message(mem_msg)
            else:
                send_msg = OpenAIMessage(role="user", content=base_prompt)
                mem_msg = OpenAIMessage(role="user", content=base_prompt)
                final_messages = [*messages_wo_user, send_msg]
                self._add_message(mem_msg)

            async for tok in self.chat_llm.chat_completion(  # type: ignore[attr-defined]
                final_messages,  # type: ignore[arg-type]
                system=self.chat_system_prompt,
                stream_=True,
            ):
                yield tok
            return

        # ==============================
        # B) chat_model 不支持 vision：按图存在情况调用 0/1/2 次 vision_summary，然后拼四段 prompt
        # ==============================
        tool_sum = None
        user_sum = None
        if user_up_b64:
            user_ref = self._img_ref_from_b64(user_up_b64, user_up_mime or "image/jpeg")
            user_sum = await self._get_vision_summary(
                user_input=user_input_text,
                img_ref=user_ref,
                b64=user_up_b64,
                mime=user_up_mime or "image/jpeg",
            )

        full_prompt = self._build_prompt_with_image_summaries(
            user_input_text=user_input_text,
            tools_summary_str=tools_summary_str,
            tool_image_summary=tool_sum,
            user_image_summary=user_sum,
        )

        send_msg = OpenAIMessage(role="user", content=full_prompt)
        mem_msg = OpenAIMessage(role="user", content=full_prompt)  # ✅ history 不含 base64
        final_messages = [*messages_wo_user, send_msg]
        self._add_message(mem_msg)

        async for tok in self.chat_llm.chat_completion(  # type: ignore[attr-defined]
            final_messages,  # type: ignore[arg-type]
            system=self.chat_system_prompt,
            stream_=True,
        ):
            yield tok

    # ---------------------------------------------------------------------
    # Transformer pipeline binding (kept!)
    # ---------------------------------------------------------------------
    def _chat_function_factory(
        self,
        chat_func: Callable[[list[OpenAIMessage]], AsyncIterator[str]],
    ) -> Callable[..., AsyncIterator[SentenceOutput | AudioOutput]]:
        @tts_filter(self.tts_preprocessor_config)
        @display_processor()
        @actions_extractor(self._live2d_model)
        @sentence_divider(
            faster_first_response=self.faster_first_response,
            segment_method=self.segment_method,
            valid_tags=["think"],
        )
        async def chat_with_memory(input_data: BatchInput) -> AsyncIterator[str | AudioOutput]:
            # ✅ 这里要用“可能带图”的 user message
            user_msg = self._build_user_message_from_batch(input_data)

            # build messages WITHOUT system (system is passed separately)
            messages: list[OpenAIMessage] = [*self._memory, user_msg]

            token_stream = chat_func(messages)
            complete_response = ""

            async for token in token_stream:
                yield token
                complete_response += token

            # store assistant message
            self._add_message(OpenAIMessage(role="assistant", content=complete_response))

        return chat_with_memory

    async def chat(self, input_data: BatchInput):  # type: ignore[override]
        return self.chat(input_data)  # type: ignore[return-value]

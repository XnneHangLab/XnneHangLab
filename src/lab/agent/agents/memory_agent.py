from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

from lab.agent.agents.agent_interface import AgentInterface
from lab.agent.input_types import BatchInput, TextSource
from lab.agent.mcp_tool_loop import McpToolLoopRunner
from lab.agent.transformers import actions_extractor, display_processor, sentence_divider, tts_filter
from lab.chat_history_manager import get_history
from lab.mcp.fastmcp_router import FastMcpRouter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from lab.agent.output_types import AudioOutput, DisplayText, SentenceOutput
    from lab.config_manager.vtuber import TTSPreprocessorConfig
    from lab.live2d_model import Live2dModel


class MemoryAgent(AgentInterface):
    """A single agent that can run in two modes:

    - enable_tool=False (default): Basic memory chat (streaming)
    - enable_tool=True: MCP tool loop (non-stream) + final chat streaming

    Final output ALWAYS goes through the transformer pipeline for TTS (same as BasicMemoryAgent).
    """

    _system: str = (
        "You are an error message repeater.\n"
        "Your job is repeating this error message:\n"
        "'No system prompt set. Please set a system prompt'.\n"
        "Don't say anything else.\n"
    )

    def __init__(
        self,
        *,
        chat_llm: Any,
        system: str,
        live2d_model: Live2dModel,
        tts_preprocessor_config: TTSPreprocessorConfig,
        enable_tool: bool = False,
        tool_llm: Any | None = None,
        mcp: FastMcpRouter | None = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
        interrupt_method: Literal["system", "user"] = "user",
    ) -> None:
        super().__init__()
        self._memory: list[dict[str, str]] = []
        self._chat_llm = chat_llm

        self.enable_tool = enable_tool
        self._tool_llm = tool_llm or chat_llm
        self.mcp = mcp or FastMcpRouter(prefix_delim="__")
        self._tool_loop = McpToolLoopRunner(tool_llm=self._tool_llm, mcp=self.mcp)

        self._live2d_model = live2d_model
        self._tts_preprocessor_config = tts_preprocessor_config
        self._faster_first_response = faster_first_response
        self._segment_method = segment_method
        self.interrupt_method = interrupt_method
        self._interrupt_handled = False

        self.set_system(system)

        # bind chat pipeline
        self.chat = self._chat_function_factory(self._stream_chat_tokens)  # type: ignore[method-assign]

        logger.info(f"MemoryAgent initialized. enable_tool={self.enable_tool}")

    # ---------------------------------------------------------------------
    # MCP lifecycle
    # ---------------------------------------------------------------------
    async def connect_mcp_servers(self, servers: list[tuple[str, str]] | None = None) -> None:
        if not servers:
            return
        for name, url in servers:
            await self.mcp.connect(name=name, url=url)

    async def close(self) -> None:
        await self.mcp.close()

    # ---------------------------------------------------------------------
    # Basic memory ops
    # ---------------------------------------------------------------------
    def set_system(self, system: str) -> None:
        logger.debug(f"MemoryAgent: Setting system prompt: '''{system}'''")
        if self.interrupt_method == "user":
            system = f"{system}\n\nIf you received `[interrupted by user]` signal, you were interrupted."
        self._system = system

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
                    "role": "user" if msg["role"] == "human" else "assistant",
                    "content": msg["content"],
                }
            )

    def handle_interrupt(self, heard_response: str) -> None:
        if self._interrupt_handled:
            return
        self._interrupt_handled = True

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
    async def _stream_chat_tokens(self, messages: list[dict[str, object]]) -> AsyncIterator[str]:
        if not self.enable_tool:
            async for tok in self._chat_llm.chat_completion(  # type: ignore[attr-defined]
                messages,  # type: ignore[arg-type]
                self._system,
                stream_=True,
            ):
                yield tok
            return

        # tool mode
        try:
            available_tools = await self.mcp.list_tools_openai_schema()
            _, tool_trace = await self._tool_loop.run_tool_loop(
                system_prompt=self._system,
                messages=messages,
                available_tools=available_tools,
                debug=False,
            )
        except Exception as e:
            logger.exception(f"Tool loop failed, fallback to normal chat: {e}")
            tool_trace = []

        tool_summary = json.dumps(
            [t.model_dump(exclude_none=True) for t in tool_trace],  # type: ignore[attr-defined]
            ensure_ascii=False,
            indent=2,
        )

        system_with_tools = (
            f"{self._system}\n\n"
            "你已经通过工具拿到结构化结果（JSON）。"
            "请基于这些结果用自然口语回答，并让输出适合 TTS 朗读（避免太‘机器格式’）。\n\n"
            f"工具结果摘要：\n{tool_summary}"
        )

        async for tok in self._chat_llm.chat_completion(  # type: ignore[attr-defined]
            messages,  # type: ignore[arg-type]
            system_with_tools,
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

        @tts_filter(self._tts_preprocessor_config)
        @display_processor()
        @actions_extractor(self._live2d_model)
        @sentence_divider(
            faster_first_response=self._faster_first_response,
            segment_method=self._segment_method,
            valid_tags=["think"],
        )
        async def chat_with_memory(input_data: BatchInput) -> AsyncIterator[str | AudioOutput]:
            user_prompt = self._to_text_prompt(input_data)

            # build messages WITHOUT system (system is passed separately)
            messages: list[dict[str, object]] = [*self._memory, {"role": "user", "content": user_prompt}]  # type: ignore[arg-type]

            # store user message
            self._add_message(user_prompt, "user")

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


# Backward-compatible alias (optional):
BasicMemoryAgent = MemoryAgent

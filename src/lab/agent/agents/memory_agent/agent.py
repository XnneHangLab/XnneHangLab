from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from loguru import logger

from lab.agent.agents.agent_interface import AgentInterface
from lab.agent.transformers import actions_extractor, display_processor, sentence_divider, tts_filter
from lab.mcp import FastMcpRouter, OpenAIMessage

from .memory_store import MemoryStore
from .message_factory import MessageFactory
from .types import ImagePayload

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from lab.agent.core import AgentCore
    from lab.agent.input_types import BatchInput
    from lab.agent.output_types import AudioOutput, SentenceOutput
    from lab.config_manager.config import XnneHangLabSettings
    from lab.config_manager.vtuber import TTSPreprocessorConfig
    from lab.live2d_model import Live2dModel


class MemoryAgent(AgentInterface):
    """MemoryAgent：编排层，将 AgentCore 的 token 流接入 TTS/Live2D pipeline。

    AgentCore 负责：tool loop、vision 摘要、prompt 组装、chat LLM 调用、历史存储。
    MemoryAgent 负责：句子切分、TTS、Live2D 动作提取、MemoryStore 写回。
    """

    def __init__(
        self,
        *,
        lab_settings: XnneHangLabSettings,
        core: AgentCore,
        live2d_model: Live2dModel,
        tts_preprocessor_config: TTSPreprocessorConfig,
        mcp: FastMcpRouter | None = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
        interrupt_method: Literal["system", "user"] = "user",
    ) -> None:
        """初始化 MemoryAgent。

        Args:
            lab_settings: 全局应用配置。
            core: 已构造好的 AgentCore 实例（必传）。
            live2d_model: 动作提取所需的 Live2D 模型。
            tts_preprocessor_config: TTS 预处理配置。
            mcp: 兼容旧生命周期的 MCP Router。
            faster_first_response: 是否优先优化首句响应延迟。
            segment_method: 句子切分方式。
            interrupt_method: 中断写入 memory 的方式。

        Returns:
            None。
        """
        super().__init__()

        self.lab_settings = lab_settings
        self.core = core
        # MemoryAgent 自身通过 _chat_function_factory 管理 MemoryStore 写回，
        # 关掉 AgentCore 的写回避免 assistant message 双写。
        self.core.write_back = False

        # MCP（兼容旧生命周期）
        self.mcp = mcp or FastMcpRouter(prefix_delim="__")

        self.msg = MessageFactory()
        self.memory = MemoryStore()
        self.memory.set_interrupt_method(interrupt_method)

        self._live2d_model = live2d_model
        self.tts_preprocessor_config = tts_preprocessor_config
        self.faster_first_response = faster_first_response
        self.segment_method = segment_method

        # bind chat pipeline
        self._bound_chat: Callable[[BatchInput], AsyncIterator[SentenceOutput | AudioOutput]] = (
            self._chat_function_factory(self._core_stream)
        )
        logger.info("MemoryAgent initialized (AgentCore mode).")

    # ---------------------------------------------------------------------
    # MCP lifecycle
    # ---------------------------------------------------------------------
    async def connect_mcp_servers(self, servers: list[tuple[str, str]] | None = None) -> None:
        """Connect MCP servers for compatibility with the existing lifecycle.

        Args:
            servers: Optional `(name, url)` pairs to connect.

        Returns:
            None.
        """
        if servers:
            for name, url in servers:
                await self.mcp.connect(name=name, url=url)
            return
        logger.info("No builtin MCP servers to connect.")

    async def close(self) -> None:
        """Close MCP resources owned by the agent.

        Returns:
            None.
        """
        await self.mcp.close()

    # ---------------------------------------------------------------------
    # Public helpers for history/interrupt (backward-compat)
    # ---------------------------------------------------------------------
    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """Load memory state from a stored history.

        Args:
            conf_uid: Configuration identifier.
            history_uid: History identifier.

        Returns:
            None.
        """
        self.memory.set_memory_from_history(conf_uid, history_uid)

    def handle_interrupt(self, heard_response: str) -> None:
        """Record a user interruption against the current response.

        Args:
            heard_response: Partial response heard by the user.

        Returns:
            None.
        """
        self.memory.handle_interrupt(heard_response)

    def reset_interrupt(self) -> None:
        """Reset interrupt tracking state.

        Returns:
            None.
        """
        self.memory.reset_interrupt()

    # ---------------------------------------------------------------------
    # Core streaming via AgentCore
    # ---------------------------------------------------------------------
    async def _core_stream(self, messages: list[OpenAIMessage]) -> AsyncIterator[str]:
        """将 MemoryAgent 的输入消息转交给 AgentCore。

        Args:
            messages: 当前轮构造出的消息列表，最后一条必须是用户消息。

        Returns:
            AgentCore 输出的 token 流。
        """
        assert messages and messages[-1].role == "user", "last message must be user"
        user_text, user_up_images = self.msg.extract_text_and_data_images(messages[-1])
        user_images = [
            ImagePayload(label=f"p{i + 1}", b64=b64, mime=mime, source="upload")
            for i, (b64, mime) in enumerate(user_up_images)
        ]
        async for token in self.core.run_turn(
            user_text=user_text,
            user_images=user_images,
        ):
            yield token
        # AgentCore.write_back=False，这里补写 user message 到 MemoryStore，
        # assistant 由 _chat_function_factory 统一写回。
        self.memory.add_message(OpenAIMessage(role="user", content=user_text))

    # ---------------------------------------------------------------------
    # Transformer pipeline
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
            user_msg = self.msg.build_user_message_from_batch(input_data)
            messages: list[OpenAIMessage] = [*self.memory.messages, user_msg]

            token_stream = chat_func(messages)
            complete_response = ""

            async for token in token_stream:
                yield token
                complete_response += token

            self.memory.add_message(OpenAIMessage(role="assistant", content=complete_response))

        return chat_with_memory

    async def chat(self, input_data: BatchInput) -> AsyncIterator[SentenceOutput | AudioOutput]:  # type: ignore[override]
        """运行一轮聊天流程。

        Args:
            input_data: 当前轮的批量输入，包含文本和可选图片。

        Returns:
            句子片段或音频片段的异步迭代器。
        """
        async for chunk in self._bound_chat(input_data):
            yield chunk

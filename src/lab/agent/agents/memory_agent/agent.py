from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from loguru import logger

from lab.agent.agent_tool_loop import AgentToolLoop
from lab.agent.agents.agent_interface import AgentInterface
from lab.agent.transformers import actions_extractor, display_processor, sentence_divider, tts_filter
from lab.mcp import ConversationState, FastMcpRouter, OpenAIMessage

from .agent_tool_loop_runner import AgentToolLoopRunner, AgentToolLoopRunResult
from .memory_store import MemoryStore
from .message_factory import MessageFactory
from .prompt_builder import PromptBuilder
from .types import ImagePayload
from .vision_summarizer import VisionSummarizer

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

    from lab.agent.core import AgentCore
    from lab.agent.input_types import BatchInput
    from lab.agent.output_types import AudioOutput, SentenceOutput
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.config_manager.config import XnneHangLabSettings
    from lab.config_manager.vtuber import TTSPreprocessorConfig
    from lab.live2d_model import Live2dModel
    from lab.tools import AgentContext, ToolManager


class MemoryAgent(AgentInterface):
    """拆分后的 MemoryAgent：仅负责编排（orchestration）。

    模式矩阵：
    - enable_tool: 是否先运行 MCP tool loop，再进行最终 chat
    - chat_supports_vision: chat_model 是否支持 image input
    - require_detailed: 逐图（N 次）vs 一次多图（1 次）生成 vision 摘要（当需要摘要时）

    不变量：
    - history/memory 不写入 base64，仅写入最终发送给 chat 的纯文本 prompt
    - tool 回调图与用户上传图语义隔离（tool 默认单张，label=tool1）
    """

    def __init__(
        self,
        *,
        lab_settings: XnneHangLabSettings,
        chat_llm: AsyncLLM,
        tool_llm: AsyncLLM,
        vision_llm: AsyncLLM,
        chat_system_prompt: str,
        tool_system_prompt: str = "",
        vision_system_prompt: str,
        live2d_model: Live2dModel,
        tts_preprocessor_config: TTSPreprocessorConfig,
        enable_tool: bool = False,
        mcp: FastMcpRouter | None = None,
        tool_manager: ToolManager | None = None,
        agent_context: AgentContext | None = None,
        workspace_root: Path | None = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
        interrupt_method: Literal["system", "user"] = "user",
        core: AgentCore | None = None,
    ) -> None:
        """初始化 MemoryAgent。

        Args:
            lab_settings: 全局应用配置。
            chat_llm: 最终回复使用的聊天模型。
            tool_llm: 工具调用使用的模型。
            vision_llm: 图片摘要使用的视觉模型。
            chat_system_prompt: Chat 模型系统提示词。
            tool_system_prompt: Tool 模型系统提示词。
            vision_system_prompt: Vision 模型系统提示词。
            live2d_model: 动作提取所需的 Live2D 模型。
            tts_preprocessor_config: TTS 预处理配置。
            enable_tool: 是否启用工具调用。
            mcp: 兼容旧生命周期的 MCP Router。
            tool_manager: 内置工具管理器。
            agent_context: 工具运行上下文。
            workspace_root: 用于兜底构造 AgentContext 的工作区根目录。
            faster_first_response: 是否优先优化首句响应延迟。
            segment_method: 句子切分方式。
            interrupt_method: 中断写入 memory 的方式。
            core: 可选的 AgentCore，传入后优先复用统一核心流程。

        Returns:
            None。
        """
        super().__init__()

        self.lab_settings = lab_settings
        self.state = ConversationState()
        self.core = core
        # MemoryAgent 自身通过 _chat_function_factory 管理存储写回，
        # 关掉 AgentCore 的写回避免 assistant message 双写。
        if self.core is not None:
            self.core._write_back = False

        # LLMs
        self.chat_llm = chat_llm
        self.tool_llm = tool_llm
        self.vision_llm = vision_llm

        self.chat_system_prompt = chat_system_prompt
        self.vision_system_prompt = vision_system_prompt

        # switches
        self.chat_supports_vision = self.lab_settings.agent.chat_model.support_vision
        self.max_vision_concurrency = lab_settings.agent.max_vision_concurrency
        self.require_detailed = lab_settings.agent.require_detailed

        # MCP
        self.enable_tool = enable_tool
        self.mcp = mcp or FastMcpRouter(prefix_delim="__")

        # ToolManager + AgentContext
        self.tool_manager = tool_manager
        if agent_context is not None:
            self.agent_context = agent_context
        elif workspace_root is not None:
            from lab.tools.types import AgentContext as _AgentContext

            self.agent_context: AgentContext | None = _AgentContext(workspace_root=workspace_root)
        else:
            self.agent_context = None

        # tool_system_prompt：优先用外部传入，否则从 tool_manager 自动生成
        if tool_system_prompt:
            self.tool_system_prompt = tool_system_prompt
        elif self.tool_manager is not None:
            self.tool_system_prompt = self.tool_manager.build_system_prompt(
                preamble="你是一个 AI 助手，可以使用以下工具来帮助完成任务：",
            )
        else:
            self.tool_system_prompt = ""

        if self.tool_manager is not None and self.agent_context is not None:
            self.tool_loop: AgentToolLoopRunner | None = AgentToolLoopRunner(
                agent_tool_loop=AgentToolLoop(
                    llm=self.tool_llm,
                    tool_manager=self.tool_manager,
                    agent_context=self.agent_context,
                )
            )
        else:
            self.tool_loop = None

        # components
        self.msg = MessageFactory()
        self.prompt = PromptBuilder()
        self.memory = MemoryStore()
        self.memory.set_interrupt_method(interrupt_method)

        self.vision = VisionSummarizer(
            vision_llm=self.vision_llm,
            vision_system_prompt=self.vision_system_prompt,
            state=self.state,
            max_concurrency=self.max_vision_concurrency,
        )

        # tts
        self._live2d_model = live2d_model
        self.tts_preprocessor_config = tts_preprocessor_config
        self.faster_first_response = faster_first_response
        self.segment_method = segment_method

        # bind chat pipeline
        self._bound_chat: Callable[[BatchInput], AsyncIterator[SentenceOutput | AudioOutput]] = (
            self._chat_function_factory(self._stream_chat_tokens)
        )
        logger.info(f"MemoryAgent initialized. enable_tool={self.enable_tool}")

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

        logger.info("No builtin MCP servers to connect. Pass servers= to connect external MCP servers.")

    async def close(self) -> None:
        """Close MCP resources owned by the agent.

        Args:
            None.

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

        Args:
            None.

        Returns:
            None.
        """
        self.memory.reset_interrupt()

    # ---------------------------------------------------------------------
    # Core streaming (with optional MCP tool loop)
    # ---------------------------------------------------------------------
    async def _stream_chat_tokens(self, messages: list[OpenAIMessage]) -> AsyncIterator[str]:
        """
        核心决策树：
        1) 根节点：enable_tool（是否先跑工具）
        2) 然后统一处理两维：
           - chat_supports_vision：chat 能不能直接吃图片
           - require_detailed：逐张（N 次）vs 一次多张（1 次）生成 upload summaries（当需要摘要时）
        3) detailed 且 chat 支持 vision：
           - 图片照样喂给 chat（带 p1/p2 标签）
           - 额外生成逐图 summaries 写入 prompt（更稳、更可解释）
        """
        assert messages and messages[-1].role == "user", "last message must be user"

        user_input_text, user_up_images = self.msg.extract_text_and_data_images(messages[-1])
        messages_wo_user = messages[:-1]

        # 1) 工具（可选）
        reuse_last_screenshot = self._should_reuse_last_screenshot(user_input_text)
        if self.tool_loop is not None:
            tool_result = await self.tool_loop.run_tool_loop_if_enabled(
                enable_tool=self.enable_tool,
                tool_system_prompt=self.tool_system_prompt,
                messages=[{"role": "user", "content": user_input_text}],
                reuse_last_screenshot=reuse_last_screenshot,
            )
        else:
            tool_result = AgentToolLoopRunResult(trace_json="(无)", final_text="", tool_image=None)

        tool_trace_json = tool_result.trace_json if self.enable_tool else None
        base_prompt = self.prompt.build_base_prompt(user_input_text=user_input_text, tool_trace_json=tool_trace_json)

        # 2) chat 不支持 vision：必须走摘要（如果没有 vision_llm 就提示）
        if not self.chat_supports_vision:
            if not self.vision_llm:
                warn = "注意：当前 chat_model 不支持图像输入，且未配置可用的 vision_model，无法读取图片内容。\n\n"
                full_prompt = warn + base_prompt
            else:
                summaries = await self.vision.summarize_all(
                    user_input_text=user_input_text,
                    tool_image=tool_result.tool_image,
                    upload_images=user_up_images,
                    require_detailed=self.require_detailed,
                )
                full_prompt = self.prompt.build_prompt_with_image_summaries(
                    user_input_text=user_input_text,
                    tools_summary_str=tool_result.trace_json if self.enable_tool else "(无)",
                    tool_image_summary=summaries.tool_image_summary,
                    user_image_summary=self.prompt.format_labeled_summaries(summaries.upload_summaries),
                )

            send_msg = OpenAIMessage(role="user", content=full_prompt)
            final_messages = [*messages_wo_user, send_msg]

            # history：只存纯文本
            self.memory.add_message(OpenAIMessage(role="user", content=full_prompt))

            async for tok in self.chat_llm.chat_completion(  # type: ignore[attr-defined]
                final_messages,  # type: ignore[arg-type]
                system=self.chat_system_prompt,
                stream_=True,
            ):
                yield tok
            return

        # 3) chat 支持 vision：快模式不做摘要；细模式做逐图摘要+图同喂给 chat
        if self.require_detailed and self.vision_llm:
            summaries = await self.vision.summarize_all(
                user_input_text=user_input_text,
                tool_image=tool_result.tool_image,  # ✅ 允许 None
                upload_images=user_up_images,  # ✅ 关键：upload-only 也要总结
                require_detailed=True,
            )
            full_prompt = self.prompt.build_prompt_with_image_summaries(
                user_input_text=user_input_text,
                tools_summary_str=tool_result.trace_json if self.enable_tool else "(无)",
                tool_image_summary=summaries.tool_image_summary,
                user_image_summary=self.prompt.format_labeled_summaries(summaries.upload_summaries),
            )
        else:
            full_prompt = base_prompt

        # 4) 构造要喂给 chat 的多图消息（带标签）
        labeled_images: list[ImagePayload] = []
        if tool_result.tool_image:
            labeled_images.append(tool_result.tool_image)
        for i, (b64, mime) in enumerate(user_up_images):
            labeled_images.append(ImagePayload(label=f"p{i + 1}", b64=b64, mime=mime, source="upload"))

        if labeled_images:
            send_msg = self.msg.user_msg_with_labeled_images(full_prompt, labeled_images)
        else:
            send_msg = OpenAIMessage(role="user", content=full_prompt)

        final_messages = [*messages_wo_user, send_msg]

        # history：只存纯文本
        self.memory.add_message(OpenAIMessage(role="user", content=full_prompt))

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
            # 用“可能带图”的 user message
            user_msg = self.msg.build_user_message_from_batch(input_data)

            # build messages WITHOUT system
            messages: list[OpenAIMessage] = [*self.memory.messages, user_msg]

            token_stream = chat_func(messages)
            complete_response = ""

            async for token in token_stream:
                yield token
                complete_response += token

            # store assistant message
            self.memory.add_message(OpenAIMessage(role="assistant", content=complete_response))

        return chat_with_memory

    async def chat(self, input_data: BatchInput) -> AsyncIterator[SentenceOutput | AudioOutput]:  # type: ignore[override]
        """运行一轮聊天流程。

        Args:
            input_data: 当前轮的批量输入，包含文本和可选图片。

        Returns:
            句子片段或音频片段的异步迭代器。
        """
        if self.core is not None:

            async def _core_stream(messages: list[OpenAIMessage]) -> AsyncIterator[str]:
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
                # AgentCore._write_back=False，这里补写 user message 到 MemoryStore，
                # assistant 由 _chat_function_factory 统一写回。
                self.memory.add_message(OpenAIMessage(role="user", content=user_text))

            bound_chat = self._chat_function_factory(_core_stream)
        else:
            bound_chat = self._bound_chat

        async for chunk in bound_chat(input_data):
            yield chunk

    @staticmethod
    def _should_reuse_last_screenshot(user_input_text: str) -> bool:
        """Return whether the user is asking to reuse the previous screenshot."""
        reuse_keywords = [
            "刚才那张截图",
            "那张截图",
            "上一个截图",
            "上一张图",
            "刚才那图",
        ]
        new_screenshot_keywords = [
            "现在截图",
            "重新截图",
            "再截",
        ]
        return any(keyword in user_input_text for keyword in reuse_keywords) and not any(
            keyword in user_input_text for keyword in new_screenshot_keywords
        )

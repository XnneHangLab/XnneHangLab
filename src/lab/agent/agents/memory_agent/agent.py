from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from loguru import logger

from lab.agent.agents.agent_interface import AgentInterface
from lab.agent.mcp_tool_loop import McpToolLoopRunner
from lab.agent.transformers import actions_extractor, display_processor, sentence_divider, tts_filter
from lab.mcp import ConversationState, FastMcpRouter, OpenAIMessage

from .memory_store import MemoryStore
from .message_factory import MessageFactory
from .prompt_builder import PromptBuilder
from .tool_runner import ToolRunner
from .types import ImagePayload
from .vision_summarizer import VisionSummarizer

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

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
    ) -> None:
        super().__init__()

        self.lab_settings = lab_settings
        self.state = ConversationState()

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

        self.tool_loop = McpToolLoopRunner(
            tool_llm=self.tool_llm,
            mcp=self.mcp,
            tool_context_config=lab_settings.mcp.tool_context,
            tool_manager=self.tool_manager,
            agent_context=self.agent_context,
        )

        # components
        self.msg = MessageFactory()
        self.prompt = PromptBuilder()
        self.memory = MemoryStore()
        self.memory.set_interrupt_method(interrupt_method)

        self.tools = ToolRunner(mcp=self.mcp, tool_loop=self.tool_loop, state=self.state)
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
        """连接 MCP servers（保持与你原实现一致）。"""
        if servers:
            for name, url in servers:
                await self.mcp.connect(name=name, url=url)
            return

        for name, s in [
            ("timeemi", self.lab_settings.mcp.servers.timeemi),
            ("vision", self.lab_settings.mcp.servers.vision),
            ("tool", self.lab_settings.mcp.servers.tool),
        ]:
            url = f"{s.transport}://{s.host}:{s.port}{s.path}"
            await self.mcp.connect(name=name, url=url)

    async def close(self) -> None:
        await self.mcp.close()

    # ---------------------------------------------------------------------
    # Public helpers for history/interrupt (backward-compat)
    # ---------------------------------------------------------------------
    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        self.memory.set_memory_from_history(conf_uid, history_uid)

    def handle_interrupt(self, heard_response: str) -> None:
        self.memory.handle_interrupt(heard_response)

    def reset_interrupt(self) -> None:
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
        available_tools = await self.mcp.list_tools_openai_schema() if self.enable_tool else []
        tool_result = await self.tools.run_tool_loop_if_enabled(
            enable_tool=self.enable_tool,
            tool_system_prompt=self.tool_system_prompt,
            available_tools=available_tools,
            user_input_text=user_input_text,
        )

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
        async for chunk in self._bound_chat(input_data):
            yield chunk

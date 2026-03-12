from __future__ import annotations

from typing import TYPE_CHECKING

from lab.agent.agent_tool_loop import AgentToolLoop
from lab.agent.agents.memory_agent.agent_tool_loop_runner import AgentToolLoopRunner, AgentToolLoopRunResult
from lab.agent.agents.memory_agent.message_factory import MessageFactory
from lab.agent.agents.memory_agent.prompt_builder import PromptBuilder
from lab.agent.agents.memory_agent.vision_summarizer import VisionSummarizer
from lab.mcp import ConversationState, OpenAIMessage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from lab.agent.agents.memory_agent.types import ImagePayload
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.agent.storage import ConversationStorage
    from lab.profile.context_injector import ContextInjector
    from lab.tools import AgentContext, ToolManager


class AgentCore:
    """统一封装 Agent 的 tool loop、vision 和 chat 主流程。"""

    def __init__(
        self,
        *,
        chat_llm: AsyncLLM,
        tool_llm: AsyncLLM,
        vision_llm: AsyncLLM | None,
        tool_manager: ToolManager | None,
        agent_context: AgentContext | None,
        context_injector: ContextInjector | None,
        storage: ConversationStorage,
        chat_system_prompt: str,
        tool_system_prompt: str = "",
        vision_system_prompt: str = "",
        enable_tool: bool = False,
        max_vision_concurrency: int = 4,
        require_detailed: bool = True,
    ) -> None:
        """初始化 AgentCore。

        Args:
            chat_llm: 最终回复使用的聊天模型。
            tool_llm: 工具调用使用的模型。
            vision_llm: 图片摘要使用的视觉模型。
            tool_manager: 工具管理器。
            agent_context: 工具运行上下文。
            context_injector: 上下文注入器。
            storage: 会话存储抽象。
            chat_system_prompt: Chat 模型系统提示词。
            tool_system_prompt: Tool 模型系统提示词。
            vision_system_prompt: Vision 模型系统提示词。
            enable_tool: 是否启用工具调用。
            max_vision_concurrency: Vision 摘要最大并发数。
            require_detailed: 是否启用逐图详细摘要。

        Returns:
            None。
        """
        self.chat_llm = chat_llm
        self.tool_llm = tool_llm
        self.vision_llm = vision_llm
        self.tool_manager = tool_manager
        self.agent_context = agent_context
        self.context_injector = context_injector
        self.storage = storage
        self.chat_system_prompt = chat_system_prompt
        self.vision_system_prompt = vision_system_prompt
        self.enable_tool = enable_tool
        self.max_vision_concurrency = max_vision_concurrency
        self.require_detailed = require_detailed
        self.chat_supports_vision = False

        if tool_system_prompt:
            self.tool_system_prompt = tool_system_prompt
        elif tool_manager is not None:
            self.tool_system_prompt = tool_manager.build_system_prompt(
                preamble="你是一个 AI 助手，可以使用以下工具来帮助完成任务：",
            )
        else:
            self.tool_system_prompt = ""

        self.state = ConversationState()
        self.msg = MessageFactory()
        self.prompt = PromptBuilder()
        self.vision = (
            VisionSummarizer(
                vision_llm=vision_llm,
                vision_system_prompt=vision_system_prompt,
                state=self.state,
                max_concurrency=max_vision_concurrency,
            )
            if vision_llm is not None
            else None
        )

        if tool_manager is not None and agent_context is not None:
            self.tool_loop: AgentToolLoopRunner | None = AgentToolLoopRunner(
                agent_tool_loop=AgentToolLoop(
                    llm=self.tool_llm,
                    tool_manager=tool_manager,
                    agent_context=agent_context,
                )
            )
        else:
            self.tool_loop = None

    async def run_turn(
        self,
        *,
        user_text: str,
        user_images: list[ImagePayload] | None = None,
        memory_context: str | None = None,
        diary_context: str | None = None,
    ) -> AsyncIterator[str]:
        """运行一轮完整的 Agent 对话流程。

        Args:
            user_text: 用户输入文本。
            user_images: 用户上传图片列表。
            memory_context: 外部检索到的记忆上下文，由调用方负责检索后传入。
            diary_context: 外部读取的日记上下文，由调用方负责读取后传入。

        Returns:
            流式输出的回复 token。
        """
        history = self.storage.load()
        user_images = user_images or []

        context_prompt = None
        if self.context_injector is not None:
            context_prompt = self.context_injector.build_context_prompt(
                memory_context=memory_context,
                diary_context=diary_context,
            )

        effective_user_text = user_text
        if context_prompt:
            effective_user_text = f"{context_prompt}\n\n{user_text}"

        reuse_last_screenshot = self._should_reuse_last_screenshot(user_text)
        if self.tool_loop is not None:
            tool_result = await self.tool_loop.run_tool_loop_if_enabled(
                enable_tool=self.enable_tool,
                tool_system_prompt=self.tool_system_prompt,
                messages=[{"role": "user", "content": effective_user_text}],
                reuse_last_screenshot=reuse_last_screenshot,
            )
        else:
            tool_result = AgentToolLoopRunResult(trace_json="(无)", final_text="", tool_image=None)

        tool_trace_json = tool_result.trace_json if self.enable_tool else None
        base_prompt = self.prompt.build_base_prompt(
            user_input_text=effective_user_text,
            tool_trace_json=tool_trace_json,
        )

        final_messages: list[OpenAIMessage]
        if not self.chat_supports_vision:
            if (tool_result.tool_image or user_images) and self.vision is None:
                warn = "注意：当前 chat_model 不支持图像输入，且未配置可用的 vision_model，无法读取图片内容。\n\n"
                full_prompt = warn + base_prompt
            elif self.vision is not None:
                summaries = await self.vision.summarize_all(
                    user_input_text=effective_user_text,
                    tool_image=tool_result.tool_image,
                    upload_images=[(image.b64, image.mime) for image in user_images],
                    require_detailed=self.require_detailed,
                )
                full_prompt = self.prompt.build_prompt_with_image_summaries(
                    user_input_text=effective_user_text,
                    tools_summary_str=tool_result.trace_json if self.enable_tool else "(无)",
                    tool_image_summary=summaries.tool_image_summary,
                    user_image_summary=self.prompt.format_labeled_summaries(summaries.upload_summaries),
                )
            else:
                full_prompt = base_prompt

            final_messages = [*history, OpenAIMessage(role="user", content=full_prompt)]
        else:
            if self.require_detailed and self.vision is not None:
                summaries = await self.vision.summarize_all(
                    user_input_text=effective_user_text,
                    tool_image=tool_result.tool_image,
                    upload_images=[(image.b64, image.mime) for image in user_images],
                    require_detailed=True,
                )
                full_prompt = self.prompt.build_prompt_with_image_summaries(
                    user_input_text=effective_user_text,
                    tools_summary_str=tool_result.trace_json if self.enable_tool else "(无)",
                    tool_image_summary=summaries.tool_image_summary,
                    user_image_summary=self.prompt.format_labeled_summaries(summaries.upload_summaries),
                )
            else:
                full_prompt = base_prompt

            labeled_images: list[ImagePayload] = []
            if tool_result.tool_image:
                labeled_images.append(tool_result.tool_image)
            labeled_images.extend(user_images)

            if labeled_images:
                final_messages = [*history, self.msg.user_msg_with_labeled_images(full_prompt, labeled_images)]
            else:
                final_messages = [*history, OpenAIMessage(role="user", content=full_prompt)]

        complete_response = ""
        async for token in self.chat_llm.chat_completion(
            final_messages,
            system=self.chat_system_prompt,
            stream_=True,
        ):
            yield token
            complete_response += token

        self.storage.append("user", user_text)
        self.storage.append("assistant", complete_response)

    @staticmethod
    def _should_reuse_last_screenshot(user_input_text: str) -> bool:
        """判断当前输入是否要求复用上一张截图。

        Args:
            user_input_text: 用户输入文本。

        Returns:
            是否应复用上一张截图。
        """
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

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
        self._write_back = True  # 设为 False 时 run_turn 不写回 storage（由外层调用方负责）

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

        # —— 背景上下文 ContextEntry（brief 由调用方提供；暂无则为 None）——
        mem_entry = self.prompt.make_context_entry(memory_context, brief=None) if memory_context else None
        diary_entry = self.prompt.make_context_entry(diary_context, brief=None) if diary_context else None

        # —— Tool loop ——
        reuse_last_screenshot = self._should_reuse_last_screenshot(user_text)
        if self.tool_loop is not None:
            tool_result = await self.tool_loop.run_tool_loop_if_enabled(
                enable_tool=self.enable_tool,
                tool_system_prompt=self.tool_system_prompt,
                messages=[{"role": "user", "content": user_text}],
                reuse_last_screenshot=reuse_last_screenshot,
            )
        else:
            tool_result = AgentToolLoopRunResult(trace_json="(无)", final_text="", tool_image=None, tool_brief=None)

        # —— Tool summary ContextEntry（brief 来自 TOOL_BRIEF 行）——
        tool_entry = (
            self.prompt.make_tool_summary(tool_result.trace_json, brief=tool_result.tool_brief)
            if self.enable_tool
            else None
        )

        # —— Vision summary ContextEntry ——
        vision_tool_entry: object = None
        vision_upload_entry: object = None

        if not self.chat_supports_vision:
            has_images = bool(tool_result.tool_image or user_images)
            if has_images and self.vision is None:
                # 没有 vision model，降级为文字警告注入 tool_entry
                warn = "注意：当前 chat_model 不支持图像输入，且未配置可用的 vision_model，无法读取图片内容。"
                tool_entry = self.prompt.make_context_entry(
                    (tool_entry.full + "\n\n" + warn) if tool_entry else warn,
                    brief="（图片未处理：无 vision model）",
                )
            elif self.vision is not None and has_images:
                summaries = await self.vision.summarize_all(
                    user_input_text=user_text,
                    tool_image=tool_result.tool_image,
                    upload_images=[(img.b64, img.mime) for img in user_images],
                    require_detailed=self.require_detailed,
                )
                if summaries.tool_image_summary:
                    vision_tool_entry = self.prompt.make_vision_tool_summary(
                        summaries.tool_image_summary,
                        brief=summaries.tool_image_brief,
                    )
                if summaries.upload_summaries:
                    vision_upload_entry = self.prompt.make_vision_upload_summary(
                        summaries.upload_summaries,
                        summaries.upload_briefs,
                    )
        else:
            # chat model 原生支持视觉时，vision 摘要仍可选做（require_detailed 控制）
            if self.require_detailed and self.vision is not None and (tool_result.tool_image or user_images):
                summaries = await self.vision.summarize_all(
                    user_input_text=user_text,
                    tool_image=tool_result.tool_image,
                    upload_images=[(img.b64, img.mime) for img in user_images],
                    require_detailed=True,
                )
                if summaries.tool_image_summary:
                    vision_tool_entry = self.prompt.make_vision_tool_summary(
                        summaries.tool_image_summary,
                        brief=summaries.tool_image_brief,
                    )
                if summaries.upload_summaries:
                    vision_upload_entry = self.prompt.make_vision_upload_summary(
                        summaries.upload_summaries,
                        summaries.upload_briefs,
                    )

        # —— 组装 UserPromptBlock ——
        from lab.agent.agents.memory_agent.user_prompt_block import ContextEntry

        user_block = self.prompt.build(
            user_text=user_text,
            memory_context=mem_entry,
            diary_context=diary_entry,
            tool_summary=tool_entry,
            vision_tool_summary=vision_tool_entry if isinstance(vision_tool_entry, ContextEntry) else None,
            vision_upload_summary=vision_upload_entry if isinstance(vision_upload_entry, ContextEntry) else None,
        )

        # —— 构建发往 LLM 的消息列表 ——
        rendered_user_content = user_block.render(condensed=False)

        if self.chat_supports_vision:
            labeled_images: list[ImagePayload] = []
            if tool_result.tool_image:
                labeled_images.append(tool_result.tool_image)
            labeled_images.extend(user_images)
            if labeled_images:
                current_user_msg = self.msg.user_msg_with_labeled_images(rendered_user_content, labeled_images)
            else:
                current_user_msg = OpenAIMessage(role="user", content=rendered_user_content)
        else:
            current_user_msg = OpenAIMessage(role="user", content=rendered_user_content)

        final_messages: list[OpenAIMessage] = [*history, current_user_msg]

        # —— 调用 chat LLM ——
        complete_response = ""
        async for token in self.chat_llm.chat_completion(
            final_messages,
            system=self.chat_system_prompt,
            stream_=True,
        ):
            yield token
            complete_response += token

        # —— 写回存储 ——
        if self._write_back:
            self.storage.append_turn(user_block, complete_response)

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

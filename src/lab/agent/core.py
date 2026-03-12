from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from lab.agent.agents.memory_agent.message_factory import MessageFactory
from lab.agent.agents.memory_agent.prompt_builder import PromptBuilder
from lab.agent.agents.memory_agent.vision_summarizer import VisionSummarizer
from lab.mcp import ConversationState, OpenAIMessage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from lab.agent.agents.memory_agent.types import ImagePayload
    from lab.agent.agents.memory_agent.user_prompt_block import ContextEntry
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.agent.storage import ConversationStorage
    from lab.profile.context_injector import ContextInjector
    from lab.tools import AgentContext, ToolManager


_TOOL_STATUS_ARG_KEYS: dict[str, tuple[str, ...]] = {
    "list_dir": ("path", "show_hidden"),
    "read_file": ("path", "start_line", "end_line"),
    "write_file": ("path", "append"),
    "edit_file": ("path", "count"),
}
_DEFAULT_TOOL_STATUS_ARG_KEYS = ("path", "query", "q", "url")
_MAX_TOOL_STATUS_FIELDS = 2
_MAX_TOOL_STATUS_VALUE_LEN = 48


def _stringify_tool_status_value(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = str(value)
    elif isinstance(value, str):
        text = " ".join(value.split())
    else:
        return None

    if not text:
        return None

    text = text.replace("[", "(").replace("]", ")")
    if len(text) > _MAX_TOOL_STATUS_VALUE_LEN:
        text = text[: _MAX_TOOL_STATUS_VALUE_LEN - 3] + "..."
    return text


def _extract_tool_status_args(tool_name: str, args_json: str) -> list[str]:
    if not args_json.strip():
        return []

    try:
        args = json.loads(args_json)
    except json.JSONDecodeError:
        return []

    if not isinstance(args, dict):
        return []

    preferred_keys = _TOOL_STATUS_ARG_KEYS.get(tool_name, _DEFAULT_TOOL_STATUS_ARG_KEYS)
    parts: list[str] = []

    for key in preferred_keys:
        if key not in args:
            continue
        value_text = _stringify_tool_status_value(args[key])
        if value_text is None:
            continue
        parts.append(f"{key}={value_text}")
        if len(parts) >= _MAX_TOOL_STATUS_FIELDS:
            break

    return parts


def _format_tool_status_token(tool_name: str, args_json: str = "") -> str:
    """Emit a display-only marker so the UI can show tool activity immediately."""
    name = tool_name.strip() or "tool"
    arg_parts = _extract_tool_status_args(name, args_json)
    suffix = f" {' '.join(arg_parts)}" if arg_parts else ""
    return f"<tool>[🔧 {name}{suffix}]</tool>"


format_tool_status_token = _format_tool_status_token


class AgentCore:
    """统一封装 Agent 的 tool loop、vision 和 chat 主流程。"""

    def __init__(
        self,
        *,
        chat_llm: AsyncLLM,
        vision_llm: AsyncLLM | None,
        tool_manager: ToolManager | None,
        agent_context: AgentContext | None,
        context_injector: ContextInjector | None,
        storage: ConversationStorage,
        chat_system_prompt: str,
        vision_system_prompt: str = "",
        enable_tool: bool = False,
        max_vision_concurrency: int = 4,
        require_detailed: bool = True,
    ) -> None:
        """初始化 AgentCore。

        Args:
            chat_llm: 最终回复使用的聊天模型。
            vision_llm: 图片摘要使用的视觉模型。
            tool_manager: 工具管理器。
            agent_context: 工具运行上下文。
            context_injector: 上下文注入器。
            storage: 会话存储抽象。
            chat_system_prompt: Chat 模型系统提示词。
            vision_system_prompt: Vision 模型系统提示词。
            enable_tool: 是否启用工具调用。
            max_vision_concurrency: Vision 摘要最大并发数。
            require_detailed: 是否启用逐图详细摘要。

        Returns:
            None。
        """
        self.chat_llm = chat_llm
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
        self.write_back = True  # 设为 False 时 run_turn 不写回 storage（由外层调用方负责）

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
        tool_image = None

        # —— 背景上下文 ContextEntry（brief 由调用方提供；暂无则为 None）——
        mem_entry = self.prompt.make_context_entry(memory_context, brief=None) if memory_context else None
        diary_entry = self.prompt.make_context_entry(diary_context, brief=None) if diary_context else None

        # —— Vision summary ContextEntry ——
        vision_tool_entry: ContextEntry | None = None
        vision_upload_entry: ContextEntry | None = None

        if not self.chat_supports_vision:
            has_images = bool(tool_image or user_images)
            if has_images and self.vision is None:
                # 没有 vision model，降级为文字警告注入 memory_context
                warn = "注意：当前 chat_model 不支持图像输入，且未配置可用的 vision_model，无法读取图片内容。"
                mem_entry = self.prompt.make_context_entry(
                    ((mem_entry.full + "\n\n" + warn) if mem_entry else warn),
                    brief=mem_entry.brief if mem_entry else "（图片未处理：无 vision model）",
                )
            elif self.vision is not None and has_images:
                summaries = await self.vision.summarize_all(
                    user_input_text=user_text,
                    tool_image=tool_image,
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
            if self.require_detailed and self.vision is not None and (tool_image or user_images):
                summaries = await self.vision.summarize_all(
                    user_input_text=user_text,
                    tool_image=tool_image,
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
        user_block = self.prompt.build(
            user_text=user_text,
            memory_context=mem_entry,
            diary_context=diary_entry,
            vision_tool_summary=vision_tool_entry,
            vision_upload_summary=vision_upload_entry,
        )

        # —— 构建发往 LLM 的消息列表 ——
        rendered_user_content = user_block.render(condensed=False)

        if self.chat_supports_vision:
            labeled_images: list[ImagePayload] = []
            if tool_image:
                labeled_images.append(tool_image)
            labeled_images.extend(user_images)
            if labeled_images:
                current_user_msg = self.msg.user_msg_with_labeled_images(rendered_user_content, labeled_images)
            else:
                current_user_msg = OpenAIMessage(role="user", content=rendered_user_content)
        else:
            current_user_msg = OpenAIMessage(role="user", content=rendered_user_content)

        final_messages: list[OpenAIMessage] = [*history, current_user_msg]
        tools_schema = self.tool_manager.list_tools_schema() if (self.enable_tool and self.tool_manager) else None

        # —— 调用 chat LLM（原生 streaming tool-calling）——
        complete_response = ""
        max_rounds = 6

        for _ in range(max_rounds):
            text_buf = ""
            tool_calls_buf: dict[int, dict[str, str]] = {}
            finish_reason: str | None = None

            async for chunk in self.chat_llm.stream_with_tools(
                final_messages,
                system=self.chat_system_prompt,
                tools=tools_schema,
            ):
                choice = chunk.choices[0] if chunk.choices else None
                if choice is None:
                    continue
                delta = choice.delta

                if delta.content:
                    text_buf += delta.content
                    complete_response += delta.content
                    yield delta.content

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_buf:
                            tool_calls_buf[idx] = {"id": tc_delta.id or "", "name": "", "arguments": ""}
                        if tc_delta.id:
                            tool_calls_buf[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_calls_buf[idx]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_calls_buf[idx]["arguments"] += tc_delta.function.arguments

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

            ordered_tool_calls = [tool_calls_buf[idx] for idx in sorted(tool_calls_buf)]
            if ordered_tool_calls:
                assistant_payload: dict[str, Any] = {
                    "role": "assistant",
                    "content": text_buf or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in ordered_tool_calls
                    ],
                }
                assistant_msg = OpenAIMessage.model_validate(assistant_payload)
            else:
                assistant_msg = OpenAIMessage(role="assistant", content=text_buf or " ")
            final_messages.append(assistant_msg)

            if finish_reason != "tool_calls" or not ordered_tool_calls:
                break

            tool_manager = self.tool_manager
            agent_context = self.agent_context
            if tool_manager is None or agent_context is None:
                break
            active_tool_manager = tool_manager
            active_agent_context = agent_context

            for tc in ordered_tool_calls:
                yield _format_tool_status_token(tc["name"], tc["arguments"])

            async def _exec_tool(
                tc_info: dict[str, str],
                bound_tool_manager: ToolManager,
                bound_agent_context: AgentContext,
            ) -> str:
                name = tc_info["name"]
                args_json = tc_info["arguments"]
                try:
                    result = await bound_tool_manager.call_tool(name, args_json, bound_agent_context)
                    return result.text if result.ok else f"Error: {result.error}"
                except Exception as exc:  # pragma: no cover - defensive path
                    return f"tool_error: {type(exc).__name__}: {exc}"

            results = await asyncio.gather(
                *(_exec_tool(tc, active_tool_manager, active_agent_context) for tc in ordered_tool_calls)
            )

            for tc_info, result_text in zip(ordered_tool_calls, results, strict=False):
                tool_msg = OpenAIMessage.model_validate(
                    {
                        "role": "tool",
                        "tool_call_id": tc_info["id"],
                        "content": result_text,
                        "name": tc_info["name"],
                    }
                )
                final_messages.append(tool_msg)

            tools_schema = active_tool_manager.list_tools_schema() if self.enable_tool else None

        # —— 写回存储 ——
        if self.write_back:
            self.storage.append_turn(user_block, complete_response)

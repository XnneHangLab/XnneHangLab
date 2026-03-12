from __future__ import annotations

import json

from lab.agent.agents.memory_agent.user_prompt_block import ContextEntry, UserPromptBlock


class PromptBuilder:
    """将各类摘要组装为结构化的 UserPromptBlock。

    设计原则：
    - 只做数据组装，不做字符串拼接细节（拼接逻辑在 UserPromptBlock.render()）
    - 不做模型调用
    """

    @staticmethod
    def build(
        *,
        user_text: str,
        memory_context: ContextEntry | None = None,
        diary_context: ContextEntry | None = None,
        tool_summary: ContextEntry | None = None,
        vision_tool_summary: ContextEntry | None = None,
        vision_upload_summary: ContextEntry | None = None,
    ) -> UserPromptBlock:
        """组装一轮对话的结构化 prompt block。

        Args:
            user_text: 原始用户输入文本。
            memory_context: 记忆检索上下文。
            diary_context: 日记摘要上下文。
            tool_summary: Tool call 执行摘要。
            vision_tool_summary: 工具截图的视觉摘要。
            vision_upload_summary: 用户上传图片的视觉摘要。

        Returns:
            组装好的 UserPromptBlock，调用 render() 获取 prompt 字符串。
        """
        block = UserPromptBlock(
            user_text=user_text,
            memory_context=memory_context,
            diary_context=diary_context,
            tool_summary=tool_summary,
            vision_tool_summary=vision_tool_summary,
            vision_upload_summary=vision_upload_summary,
        )
        block.validate()
        return block

    @staticmethod
    def make_tool_summary(trace_json: str, *, brief: str) -> ContextEntry:
        """将 tool call trace JSON 包装为可衰减的 ContextEntry。

        Args:
            trace_json: Tool call 执行的完整 JSON 轨迹。
            brief: 一句话摘要，用于历史轮次压缩。

        Returns:
            ContextEntry 实例。
        """
        return ContextEntry(full=trace_json, brief=brief)

    @staticmethod
    def make_vision_tool_summary(summary: str, *, brief: str) -> ContextEntry:
        """将工具截图的视觉摘要包装为可衰减的 ContextEntry。

        Args:
            summary: 视觉模型输出的完整摘要文本。
            brief: 一句话摘要，用于历史轮次压缩。

        Returns:
            ContextEntry 实例。
        """
        return ContextEntry(full=summary, brief=brief)

    @staticmethod
    def make_vision_upload_summary(labeled: dict[str, str], *, brief: str) -> ContextEntry:
        """将用户上传图片的多图摘要包装为可衰减的 ContextEntry。

        Args:
            labeled: 标签到摘要的映射，格式为 {"p1": "...", "p2": "..."}。
            brief: 一句话摘要，用于历史轮次压缩。

        Returns:
            ContextEntry 实例。
        """
        if not labeled:
            return ContextEntry(full="无上传图片。", brief=brief or "无上传图片。")
        lines = [json.dumps({"id": k, "summary": labeled[k]}, ensure_ascii=False) for k in sorted(labeled)]
        return ContextEntry(full="\n".join(lines), brief=brief)

    @staticmethod
    def make_context_entry(full: str, *, brief: str) -> ContextEntry:
        """通用工厂：将任意文本包装为可衰减的 ContextEntry。

        Args:
            full: 完整版内容。
            brief: 一句话简要版。

        Returns:
            ContextEntry 实例。
        """
        return ContextEntry(full=full, brief=brief)

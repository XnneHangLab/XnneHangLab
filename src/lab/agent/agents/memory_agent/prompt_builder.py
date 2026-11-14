from __future__ import annotations

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
        vision_tool_summary: ContextEntry | None = None,
        vision_upload_summary: ContextEntry | None = None,
    ) -> UserPromptBlock:
        """组装一轮对话的结构化 prompt block。

        Args:
            user_text: 原始用户输入文本。
            memory_context: 记忆检索上下文。
            vision_tool_summary: 工具截图的视觉摘要。
            vision_upload_summary: 用户上传图片的视觉摘要。

        Returns:
            组装好的 UserPromptBlock，调用 render() 获取 prompt 字符串。
        """
        block = UserPromptBlock(
            user_text=user_text,
            memory_context=memory_context,
            vision_tool_summary=vision_tool_summary,
            vision_upload_summary=vision_upload_summary,
        )
        block.validate()
        return block

    @staticmethod
    def make_context_entry(full: str, *, brief: str | None) -> ContextEntry:
        """通用工厂：将任意文本包装为可衰减的 ContextEntry。

        Args:
            full: 完整版内容。
            brief: 一句话简要版；None 表示无摘要，condensed 时整条忽略。

        Returns:
            ContextEntry 实例。
        """
        return ContextEntry(full=full, brief=brief)

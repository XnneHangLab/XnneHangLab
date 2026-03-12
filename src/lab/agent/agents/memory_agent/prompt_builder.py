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
    def make_tool_summary(trace_json: str, *, brief: str | None) -> ContextEntry:
        """将 tool call trace JSON 包装为可衰减的 ContextEntry。

        Args:
            trace_json: Tool call 执行的完整 JSON 轨迹。
            brief: 一句话摘要（来自 TOOL_BRIEF 行）；None 表示提取失败，condensed 时整条忽略。

        Returns:
            ContextEntry 实例。
        """
        return ContextEntry(full=trace_json, brief=brief)

    @staticmethod
    def make_vision_tool_summary(summary: str, *, brief: str | None) -> ContextEntry:
        """将工具截图的视觉摘要包装为可衰减的 ContextEntry。

        Args:
            summary: 视觉模型输出的完整摘要文本。
            brief: 一句话摘要（来自 scene 字段）；None 表示提取失败，condensed 时整条忽略。

        Returns:
            ContextEntry 实例。
        """
        return ContextEntry(full=summary, brief=brief)

    @staticmethod
    def make_vision_upload_summary(
        labeled: dict[str, str], briefs: dict[str, str | None], *, prefix: str = "p"
    ) -> ContextEntry:
        """将用户上传图片的多图摘要包装为可衰减的 ContextEntry。

        brief 取第一张有效 brief；若所有张均为 None，则 brief 为 None。

        Args:
            labeled: 标签到完整摘要的映射，格式为 {"p1": "...", "p2": "..."}。
            briefs: 标签到一句话摘要的映射，None 值表示该张解析失败。
            prefix: 标签前缀，用于排序（默认 "p"）。

        Returns:
            ContextEntry 实例。
        """
        if not labeled:
            return ContextEntry(full="无上传图片。", brief=None)
        lines = [json.dumps({"id": k, "summary": labeled[k]}, ensure_ascii=False) for k in sorted(labeled)]
        full = "\n".join(lines)
        # brief：多图时只取首张 scene + 图片数；单图直接用 scene
        brief_parts = [briefs.get(k) for k in sorted(labeled) if briefs.get(k)]
        if len(brief_parts) > 1:
            brief = f"{brief_parts[0]}（共{len(labeled)}张图）"
        elif brief_parts:
            brief = brief_parts[0]
        else:
            brief = None
        return ContextEntry(full=full, brief=brief)

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

    # ------------------------------------------------------------------
    # 兼容层：MemoryAgent 旧路径（_chat_function_factory）仍在使用
    # 待旧路径清理后可一并删除
    # ------------------------------------------------------------------

    @staticmethod
    def build_base_prompt(*, user_input_text: str, tool_trace_json: str | None) -> str:
        """[兼容] 构建纯文本 base prompt（旧路径使用）。"""
        parts = [f"[Task / User Prompt]\n{user_input_text}"]
        if tool_trace_json is not None:
            parts.append(f"[Tool Call Summary]\n{tool_trace_json}")
        return "\n\n###\n\n".join(parts)

    @staticmethod
    def build_prompt_with_image_summaries(
        *,
        user_input_text: str,
        tools_summary_str: str,
        tool_image_summary: str,
        user_image_summary: str,
    ) -> str:
        """[兼容] 构建含图片摘要的 prompt（旧路径使用）。"""
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

    @staticmethod
    def format_labeled_summaries(labeled: dict[str, str]) -> str:
        """[兼容] 将 {"p1": "...", "p2": "..."} 格式化为多行文本（旧路径使用）。"""
        if not labeled:
            return "无"
        lines: list[str] = []
        for k in sorted(labeled.keys()):
            lines.append(json.dumps({"id": k, "summary": labeled[k]}, ensure_ascii=False))
        return "\n".join(lines)

from __future__ import annotations

import json


class PromptBuilder:
    """负责拼接给 chat_model 的纯文本 prompt。

    设计原则：
    - 只做字符串拼接，不做模型调用
    - 让 agent.py 的分支尽量少“拼字符串细节”
    """

    @staticmethod
    def build_base_prompt(*, user_input_text: str, tool_trace_json: str | None) -> str:
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
        """把 {"p1": "...", "p2": "..."} 格式化为多行 json-like 文本。"""
        if not labeled:
            return "无"

        lines: list[str] = []
        for k in sorted(labeled.keys()):
            lines.append(json.dumps({"id": k, "summary": labeled[k]}, ensure_ascii=False))
        return "\n".join(lines)

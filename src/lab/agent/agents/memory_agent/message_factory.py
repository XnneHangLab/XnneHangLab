from __future__ import annotations

from typing import TYPE_CHECKING

from lab.agent.input_types import BatchInput, TextSource
from lab.agent.types import ContentPart, ImagePart, ImageURL, OpenAIMessage, TextPart

if TYPE_CHECKING:
    from lab.agent.agents.memory_agent.types import ImagePayload


class MessageFactory:
    """与 OpenAIMessage / ContentPart 相关的“纯构造/解析”工具。

    设计原则：
    - 不调用模型
    - 不读写 state
    - 尽量保持纯输入输出，便于测试与复用
    """

    @staticmethod
    def extract_text_and_data_images(msg: OpenAIMessage) -> tuple[str, list[tuple[str, str]]]:
        """从 OpenAIMessage 中抽取：
        - text：拼接所有 text parts
        - images：提取所有 data-url base64 图片，返回 [(b64, mime), ...]

        注意：只解析 data:...;base64,... 这种 URL。
        """
        if isinstance(msg.content, str):
            return msg.content, []

        text = ""
        images: list[tuple[str, str]] = []

        if not msg.content:
            return "", []

        for part in msg.content:
            if part.type == "text":
                text += str(part.text)
            elif part.type == "image_url":
                url = getattr(part.image_url, "url", "")
                if isinstance(url, str) and url.startswith("data:") and ";base64," in url:
                    head, _, b64data = url.partition(";base64,")
                    mime = head[5:] or "image/jpeg"
                    images.append((b64data, mime))

        return text, images

    @staticmethod
    def user_msg_with_image_from_screen_shoot(text: str, *, b64: str, mime: str = "image/jpeg") -> OpenAIMessage:
        parts: list[ContentPart] = [
            TextPart(type="text", text=text),
            ImagePart(type="image_url", image_url=ImageURL(url=f"data:{mime};base64,{b64}")),
        ]
        return OpenAIMessage(role="user", content=parts)

    @staticmethod
    def user_msg_with_upload_images(text: str, datas: list[str]) -> OpenAIMessage:
        """datas 为 data-url 列表：data:image/png;base64,..."""
        parts: list[ContentPart] = [TextPart(type="text", text=text)]
        for data in datas:
            parts.append(ImagePart(type="image_url", image_url=ImageURL(url=data)))
        return OpenAIMessage(role="user", content=parts)

    @staticmethod
    def user_msg_with_images(text: str, images: list[tuple[str, str]]) -> OpenAIMessage:
        """images: [(b64, mime), ...]"""
        parts: list[ContentPart] = [TextPart(type="text", text=text)]
        for b64, mime in images:
            parts.append(ImagePart(type="image_url", image_url=ImageURL(url=f"data:{mime};base64,{b64}")))
        return OpenAIMessage(role="user", content=parts)

    @staticmethod
    def user_msg_with_labeled_images(text: str, labeled_images: list[ImagePayload]) -> OpenAIMessage:
        """构造：文本 + 多张图片，每张图片前插入标签文本（例如 [p1]）。

        目的：
        - 多图输入时提供稳定锚点，降低串台/漏图风险
        - 与 vision summary 的标签对齐（p1/p2/..., tool1...）
        """
        parts: list[ContentPart] = [TextPart(type="text", text=text)]
        for img in labeled_images:
            parts.append(TextPart(type="text", text=f"\n\n[{img.label}]"))
            parts.append(ImagePart(type="image_url", image_url=ImageURL(url=f"data:{img.mime};base64,{img.b64}")))
        return OpenAIMessage(role="user", content=parts)

    @staticmethod
    def tool_image_handoff_text(label: str) -> str:
        return (
            "A tool callback image is attached below. "
            f"Use image [{label}] together with the preceding tool result to answer the current user request."
        )

    @staticmethod
    def tool_image_summary_handoff_text(label: str, summary: str) -> str:
        return (
            "The tool callback image was routed through the vision summarizer. "
            f"Use the summary for image [{label}] together with the preceding tool result.\n\n"
            f"[Tool Call Image Summary]\n{summary}"
        )

    # ------------------------------
    # BatchInput -> user message
    # ------------------------------
    @staticmethod
    def to_text_prompt(input_data: BatchInput) -> str:
        parts: list[str] = []
        for text_data in input_data.texts:
            if text_data.source == TextSource.INPUT:
                parts.append(text_data.content)
            elif text_data.source == TextSource.CLIPBOARD:
                parts.append(f"[Clipboard content: {text_data.content}]")
        return "\n".join(parts)

    @staticmethod
    def build_user_message_from_batch(input_data: BatchInput) -> OpenAIMessage:
        user_prompt = MessageFactory.to_text_prompt(input_data)
        if input_data.images:
            return MessageFactory.user_msg_with_upload_images(user_prompt, [img.data for img in input_data.images])
        return OpenAIMessage(role="user", content=user_prompt)

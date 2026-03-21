from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from lab.agent.types import OpenAIMessage
from lab.conversations.chat_history_manager import get_history, store_message

if TYPE_CHECKING:
    from lab.agent.output_types import DisplayText


class MemoryStore:
    """负责：
    - 内存消息列表（供下一轮 prompt）
    - 历史写入（store_message）
    - 从历史加载（get_history）
    - interrupt 处理
    """

    def __init__(self) -> None:
        self._memory: list[OpenAIMessage] = []
        self.history_uid: str | None = None
        self.conf_uid: str | None = None
        self.interrupt_method: str = "user"
        self.interrupt_handled: bool = False

    @property
    def messages(self) -> list[OpenAIMessage]:
        return list(self._memory)

    def set_interrupt_method(self, method: str) -> None:
        self.interrupt_method = method

    def add_message(self, message: OpenAIMessage, display_text: DisplayText | None = None) -> None:
        """写入 memory + 可选写入历史。

        注意：这里期望 message.content 最终存为纯文本（不含 base64）。
        """
        if isinstance(message.content, str):
            text_content = message.content
        else:
            text_content = ""
            if message.content is None:
                return
            for item in message.content:
                if item.type == "text":
                    text_content += str(item.text)

        if message.role == "assistant" and display_text is not None:
            content = display_text.text
        else:
            content = text_content

        self._memory.append(OpenAIMessage(role=message.role, content=content))
        if self.history_uid and self.conf_uid:
            store_message(
                conf_uid=self.conf_uid,
                history_uid=self.history_uid,
                role=message.role,
                content=content,
            )

    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """从历史加载 user/assistant 消息到内存。"""
        messages = get_history(conf_uid, history_uid)
        self.conf_uid = conf_uid
        self.history_uid = history_uid
        self._memory = []
        for msg in messages:
            role = msg["role"]
            if role in ("human", "user"):
                target_role = "user"
            elif role in ("ai", "assistant"):
                target_role = "assistant"
            else:
                continue

            content = msg["content"]
            if target_role == "assistant" and not content:
                logger.warning("Skip empty assistant message while rebuilding memory from history: %s", history_uid)
                continue

            self._memory.append(OpenAIMessage(role=target_role, content=content))

    def handle_interrupt(self, heard_response: str) -> None:
        if self.interrupt_handled:
            return
        self.interrupt_handled = True

        if self._memory and self._memory[-1].role == "assistant":
            self._memory[-1].content = heard_response + "..."
        elif heard_response:
            self._memory.append(OpenAIMessage(role="assistant", content=heard_response + "..."))

        self._memory.append(
            OpenAIMessage(
                role="system" if self.interrupt_method == "system" else "user",
                content="[interrupted by user]",
            )
        )

    def reset_interrupt(self) -> None:
        self.interrupt_handled = False

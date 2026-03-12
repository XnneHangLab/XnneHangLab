from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lab.mcp import OpenAIMessage

if TYPE_CHECKING:
    from lab.agent.agents.memory_agent.memory_store import MemoryStore
    from lab.conversation.store import ConversationStore


@runtime_checkable
class ConversationStorage(Protocol):
    """统一的会话存储接口。"""

    def load(self) -> list[OpenAIMessage]:
        """加载当前会话历史。

        Returns:
            当前会话的消息列表。
        """

    def append(self, role: str, content: str) -> None:
        """追加一条会话消息。

        Args:
            role: 消息角色。
            content: 消息文本内容。

        Returns:
            None。
        """

    def handle_interrupt(self, heard_response: str) -> None:
        """处理用户打断事件。

        Args:
            heard_response: 用户已经听到的部分回复。

        Returns:
            None。
        """

        return None


class MemoryStoreAdapter:
    """包装 MemoryStore，实现统一的会话存储接口。"""

    def __init__(self, store: MemoryStore) -> None:
        """初始化适配器。

        Args:
            store: 要包装的 MemoryStore 实例。

        Returns:
            None。
        """
        self._store = store

    def load(self) -> list[OpenAIMessage]:
        """加载 MemoryStore 中的消息列表。

        Returns:
            当前内存中的消息列表。
        """
        return self._store.messages

    def append(self, role: str, content: str) -> None:
        """向 MemoryStore 追加一条消息。

        Args:
            role: 消息角色。
            content: 消息文本内容。

        Returns:
            None。
        """
        self._store.add_message(OpenAIMessage(role=role, content=content))

    def handle_interrupt(self, heard_response: str) -> None:
        """委托 MemoryStore 处理用户打断。

        Args:
            heard_response: 用户已经听到的部分回复。

        Returns:
            None。
        """
        self._store.handle_interrupt(heard_response)


class ConversationStoreAdapter:
    """包装 ConversationStore，实现统一的会话存储接口。"""

    def __init__(self, store: ConversationStore, date_id: str) -> None:
        """初始化适配器。

        Args:
            store: 要包装的 ConversationStore 实例。
            date_id: 当前会话对应的日期 ID。

        Returns:
            None。
        """
        self._store = store
        self._date_id = date_id

    def load(self) -> list[OpenAIMessage]:
        """加载 ConversationStore 中的消息列表。

        Returns:
            当前日期会话的消息列表。
        """
        messages = self._store.read_conversation(self._date_id)
        return [
            OpenAIMessage(role=message["role"], content=message["content"])
            for message in messages
            if message.get("role") in ("user", "assistant")
        ]

    def append(self, role: str, content: str) -> None:
        """向 ConversationStore 追加一条消息。

        Args:
            role: 消息角色。
            content: 消息文本内容。

        Returns:
            None。
        """
        self._store.append_turn(self._date_id, role=role, content=content)

    def handle_interrupt(self, heard_response: str) -> None:
        """ConversationStore 暂不处理打断事件。

        Args:
            heard_response: 用户已经听到的部分回复。

        Returns:
            None。
        """
        return None

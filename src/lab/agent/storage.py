from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lab.agent.agents.memory_agent.user_prompt_block import UserPromptBlock
from lab.agent.types import OpenAIMessage

if TYPE_CHECKING:
    from lab.agent.agents.memory_agent.memory_store import MemoryStore
    from lab.history_storage.store import HistoryStorage

# 超过这轮数的历史 user message 使用 brief 版本，减少上下文占用。
_CONDENSE_AFTER_TURNS = 4


@runtime_checkable
class ConversationStorage(Protocol):
    """统一的会话存储接口。"""

    def load(self) -> list[OpenAIMessage]:
        """加载当前会话历史，并按策略压缩较早轮次。"""
        return []

    def append_turn(self, user_block: UserPromptBlock, assistant_text: str) -> None:
        """追加一轮完整对话。"""

    def handle_interrupt(self, heard_response: str) -> None:
        """处理用户打断事件。"""
        return None


def _render_user_content(content: str, *, condensed: bool) -> str:
    """将存储中的 user 内容渲染成最终 prompt 文本。"""
    if UserPromptBlock.is_block_content(content):
        block = UserPromptBlock.from_storage_content(content)
        return block.render(condensed=condensed)
    return content


def _build_messages_with_condensing(raw_pairs: list[tuple[str, str]]) -> list[OpenAIMessage]:
    """把按轮次配对的消息渲染成 OpenAIMessage 列表。"""
    total = len(raw_pairs)
    messages: list[OpenAIMessage] = []
    for index, (user_content, assistant_content) in enumerate(raw_pairs):
        turns_from_end = total - 1 - index
        condensed = turns_from_end >= _CONDENSE_AFTER_TURNS
        messages.append(OpenAIMessage(role="user", content=_render_user_content(user_content, condensed=condensed)))
        messages.append(OpenAIMessage(role="assistant", content=assistant_content))
    return messages


class MemoryStoreAdapter:
    """包装 MemoryStore，使其符合统一的会话存储接口。"""

    def __init__(self, store: MemoryStore) -> None:
        """初始化 MemoryStore 适配器。"""
        self._store = store

    def load(self) -> list[OpenAIMessage]:
        """读取 MemoryStore 中的消息，并压缩较早轮次。"""
        raw = self._store.messages
        pairs: list[tuple[str, str]] = []
        index = 0
        while index < len(raw) - 1:
            if raw[index].role == "user" and raw[index + 1].role == "assistant":
                user_content = raw[index].content
                assistant_content = raw[index + 1].content
                user_text = user_content if isinstance(user_content, str) else ""
                assistant_text = assistant_content if isinstance(assistant_content, str) else ""
                pairs.append((user_text, assistant_text))
                index += 2
            else:
                index += 1
        return _build_messages_with_condensing(pairs)

    def append_turn(self, user_block: UserPromptBlock, assistant_text: str) -> None:
        """向 MemoryStore 追加一轮结构化对话。"""
        self._store.add_message(OpenAIMessage(role="user", content=user_block.to_storage_content()))
        self._store.add_message(OpenAIMessage(role="assistant", content=assistant_text))

    def handle_interrupt(self, heard_response: str) -> None:
        """委托 MemoryStore 处理打断事件。"""
        self._store.handle_interrupt(heard_response)


class HistoryStorageAdapter:
    """包装历史持久化存储，使其符合统一的会话存储接口。"""

    def __init__(self, store: HistoryStorage) -> None:
        """初始化 HistoryStorage 适配器。"""
        self._store = store

    @staticmethod
    def _current_date_id() -> str:
        """获取当前 UTC 日期 ID。"""
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def load(self) -> list[OpenAIMessage]:
        """读取持久化历史，并压缩较早轮次。"""
        raw = self._store.read_conversation(self._current_date_id())
        filtered = [message for message in raw if message.get("role") in ("user", "assistant")]
        pairs: list[tuple[str, str]] = []
        index = 0
        while index < len(filtered) - 1:
            if filtered[index]["role"] == "user" and filtered[index + 1]["role"] == "assistant":
                pairs.append((filtered[index]["content"], filtered[index + 1]["content"]))
                index += 2
            else:
                index += 1
        return _build_messages_with_condensing(pairs)

    def append_turn(self, user_block: UserPromptBlock, assistant_text: str) -> None:
        """向持久化历史追加一轮结构化对话。"""
        date_id = self._current_date_id()
        self._store.append_turn(date_id, role="user", content=user_block.to_storage_content())
        self._store.append_turn(date_id, role="assistant", content=assistant_text)

    def handle_interrupt(self, heard_response: str) -> None:
        """持久化历史暂不处理打断事件。"""
        del heard_response
        return None


# 为低风险迁移保留旧名字。
ConversationStoreAdapter = HistoryStorageAdapter

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lab.agent.agents.memory_agent.user_prompt_block import UserPromptBlock
from lab.agent.types import OpenAIMessage

if TYPE_CHECKING:
    from lab.agent.agents.memory_agent.memory_store import MemoryStore
    from lab.conversation.store import ConversationStore

# 超过此轮数的历史 user message 使用 brief（condensed）渲染
_CONDENSE_AFTER_TURNS = 4


@runtime_checkable
class ConversationStorage(Protocol):
    """统一的会话存储接口。"""

    def load(self) -> list[OpenAIMessage]:
        """加载当前会话历史，超出保留轮数的轮次自动压缩为 brief 版本。

        Returns:
            当前会话的消息列表，user message content 已按需渲染。
        """
        return []

    def append_turn(self, user_block: UserPromptBlock, assistant_text: str) -> None:
        """追加一轮完整对话（user + assistant）。

        Args:
            user_block: 当前轮结构化 user prompt block。
            assistant_text: 当前轮 assistant 回复文本。

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


def _render_user_content(content: str, *, condensed: bool) -> str:
    """将存储的 user content 渲染为 prompt 字符串。

    若 content 是结构化 UserPromptBlock 格式则按需 condense；
    否则（旧纯文本）原样返回，向后兼容。

    Args:
        content: 存储中的 user message content 字符串。
        condensed: 是否压缩为 brief 版本。

    Returns:
        渲染后的字符串。
    """
    if UserPromptBlock.is_block_content(content):
        block = UserPromptBlock.from_storage_content(content)
        return block.render(condensed=condensed)
    # 旧纯文本，原样返回
    return content


def _build_messages_with_condensing(
    raw_pairs: list[tuple[str, str]],
) -> list[OpenAIMessage]:
    """将 (user_content, assistant_content) 配对列表渲染为 OpenAIMessage 列表。

    最近 _CONDENSE_AFTER_TURNS 轮保留 full，更早的轮次压缩为 brief。

    Args:
        raw_pairs: 按时间顺序排列的 (user_content, assistant_content) 列表。

    Returns:
        渲染后的 OpenAIMessage 列表。
    """
    total = len(raw_pairs)
    messages: list[OpenAIMessage] = []
    for i, (user_content, assistant_content) in enumerate(raw_pairs):
        # 距末尾的轮数（0 = 最新轮）
        turns_from_end = total - 1 - i
        condensed = turns_from_end >= _CONDENSE_AFTER_TURNS
        messages.append(OpenAIMessage(role="user", content=_render_user_content(user_content, condensed=condensed)))
        messages.append(OpenAIMessage(role="assistant", content=assistant_content))
    return messages


class MemoryStoreAdapter:
    """包装 MemoryStore，实现统一的会话存储接口。

    user message 以结构化 UserPromptBlock 存储；加载时按轮次自动 condense。
    """

    def __init__(self, store: MemoryStore) -> None:
        """初始化适配器。

        Args:
            store: 要包装的 MemoryStore 实例。
        """
        self._store = store

    def load(self) -> list[OpenAIMessage]:
        """加载 MemoryStore 中的消息列表，超出保留轮数的轮次压缩为 brief。

        Returns:
            渲染后的消息列表。
        """
        raw = self._store.messages
        # 按 user/assistant 交替配对；跳过不完整的末尾 user（不太可能，防御性处理）
        pairs: list[tuple[str, str]] = []
        i = 0
        while i < len(raw) - 1:
            if raw[i].role == "user" and raw[i + 1].role == "assistant":
                u_content = raw[i].content
                a_content = raw[i + 1].content
                u = u_content if isinstance(u_content, str) else ""
                a = a_content if isinstance(a_content, str) else ""
                pairs.append((u, a))
                i += 2
            else:
                i += 1
        return _build_messages_with_condensing(pairs)

    def append_turn(self, user_block: UserPromptBlock, assistant_text: str) -> None:
        """向 MemoryStore 追加一轮对话（结构化 user block + assistant 文本）。

        Args:
            user_block: 结构化 user prompt block。
            assistant_text: assistant 回复文本。
        """
        self._store.add_message(OpenAIMessage(role="user", content=user_block.to_storage_content()))
        self._store.add_message(OpenAIMessage(role="assistant", content=assistant_text))

    def handle_interrupt(self, heard_response: str) -> None:
        """委托 MemoryStore 处理用户打断。

        Args:
            heard_response: 用户已经听到的部分回复。
        """
        self._store.handle_interrupt(heard_response)


class ConversationStoreAdapter:
    """包装 ConversationStore，实现统一的会话存储接口。

    user message 以结构化 UserPromptBlock 存储；加载时按轮次自动 condense。
    date_id 每次调用时动态计算，避免跨午夜写入错误日期。
    """

    def __init__(self, store: ConversationStore) -> None:
        """初始化适配器。

        Args:
            store: 要包装的 ConversationStore 实例。
        """
        self._store = store

    @staticmethod
    def _current_date_id() -> str:
        """获取当前 UTC 日期 ID。

        Returns:
            格式为 YYYY-MM-DD 的日期字符串。
        """
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def load(self) -> list[OpenAIMessage]:
        """加载 ConversationStore 中的消息列表，超出保留轮数的轮次压缩为 brief。

        Returns:
            渲染后的消息列表。
        """
        raw = self._store.read_conversation(self._current_date_id())
        # 过滤出 user/assistant 消息，按顺序配对
        filtered = [m for m in raw if m.get("role") in ("user", "assistant")]
        pairs: list[tuple[str, str]] = []
        i = 0
        while i < len(filtered) - 1:
            if filtered[i]["role"] == "user" and filtered[i + 1]["role"] == "assistant":
                pairs.append((filtered[i]["content"], filtered[i + 1]["content"]))
                i += 2
            else:
                i += 1
        return _build_messages_with_condensing(pairs)

    def append_turn(self, user_block: UserPromptBlock, assistant_text: str) -> None:
        """向 ConversationStore 追加一轮对话（结构化 user block + assistant 文本）。

        Args:
            user_block: 结构化 user prompt block。
            assistant_text: assistant 回复文本。
        """
        self._store.append_turn(self._current_date_id(), role="user", content=user_block.to_storage_content())
        self._store.append_turn(self._current_date_id(), role="assistant", content=assistant_text)

    def handle_interrupt(self, heard_response: str) -> None:
        """ConversationStore 暂不处理打断事件。

        Args:
            heard_response: 用户已经听到的部分回复。
        """
        return None

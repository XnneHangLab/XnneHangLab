from __future__ import annotations

from lab.history_storage import ConversationStore, HistoryStorage


def test_history_storage_round_trip(tmp_path) -> None:
    """历史存储应能正确写入、读取并列出日期 ID。"""
    store = HistoryStorage(base_dir=str(tmp_path))

    store.append_turn("2026-03-20", role="user", content="你好")
    store.append_turn("2026-03-20", role="assistant", content="你好，我在。")

    messages = store.read_conversation("2026-03-20")

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert [message["content"] for message in messages] == ["你好", "你好，我在。"]
    assert store.list_conversations() == ["2026-03-20"]


def test_legacy_conversation_store_alias_points_to_history_storage() -> None:
    """旧名字应继续指向新的历史存储实现。"""
    assert ConversationStore is HistoryStorage

"""验证结构化 history 中 tool image context 的压缩行为。"""

from __future__ import annotations

from lab.agent.agents.memory_agent.memory_store import MemoryStore
from lab.agent.agents.memory_agent.user_prompt_block import ContextEntry, UserPromptBlock
from lab.agent.storage import MemoryStoreAdapter


def test_tool_image_context_condenses_from_full_to_brief_and_omits_missing_brief() -> None:
    """验证 tool image working context 会遵守现有的压缩策略。

    Args:
        None。

    验证点：
    - 较老轮次的 tool image context 从 full 衰减为 brief。
    - brief 为 None 的旧 context 在压缩时被省略。
    - 较新轮次仍保留 full。
    """
    store = MemoryStore()
    adapter = MemoryStoreAdapter(store, condense_after_turns=4)

    adapter.append_turn(
        UserPromptBlock(
            user_text="turn 1",
            vision_tool_summary=ContextEntry(full="old tool full", brief="old tool brief"),
        ),
        "assistant 1",
    )
    adapter.append_turn(
        UserPromptBlock(
            user_text="turn 2",
            vision_tool_summary=ContextEntry(full="tool full without brief", brief=None),
        ),
        "assistant 2",
    )
    adapter.append_turn(UserPromptBlock(user_text="turn 3"), "assistant 3")
    adapter.append_turn(UserPromptBlock(user_text="turn 4"), "assistant 4")
    adapter.append_turn(UserPromptBlock(user_text="turn 5"), "assistant 5")
    adapter.append_turn(
        UserPromptBlock(
            user_text="turn 6",
            vision_tool_summary=ContextEntry(full="recent tool full", brief="recent tool brief"),
        ),
        "assistant 6",
    )

    messages = adapter.load()

    first_user = messages[0]
    second_user = messages[2]
    latest_user = messages[10]

    assert first_user.role == "user"
    assert isinstance(first_user.content, str)
    assert "old tool brief" in first_user.content
    assert "old tool full" not in first_user.content

    assert second_user.role == "user"
    assert isinstance(second_user.content, str)
    assert "tool full without brief" not in second_user.content
    assert "[Tool Call Image Summary]" not in second_user.content

    assert latest_user.role == "user"
    assert isinstance(latest_user.content, str)
    assert "[User Input]\nturn 6" in latest_user.content
    assert "recent tool full" in latest_user.content


def test_empty_assistant_turn_is_normalized_for_storage() -> None:
    store = MemoryStore()
    adapter = MemoryStoreAdapter(store)

    adapter.append_turn(UserPromptBlock(user_text="turn 1"), "")

    messages = adapter.load()

    assert len(messages) == 2
    assert messages[1].role == "assistant"
    assert messages[1].content == " "

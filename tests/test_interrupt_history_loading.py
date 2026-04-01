"""Regression tests for interrupt history writing and legacy history loading."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from lab.agent.agents.memory_agent.memory_store import MemoryStore
from lab.conversations import conversation_handler

if TYPE_CHECKING:
    from lab.service_context import ServiceContext


@pytest.mark.anyio
async def test_handle_individual_interrupt_does_not_store_empty_assistant_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure empty interrupt text is not written as an assistant history entry."""
    recorded_calls: list[dict[str, str]] = []

    def fake_store_message(**kwargs: str) -> None:
        recorded_calls.append(kwargs)

    monkeypatch.setattr("lab.conversations.conversation_handler.store_message", fake_store_message)

    task: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(60))
    context = cast(
        "ServiceContext",
        SimpleNamespace(
            history_uid="history-1",
            character_config=SimpleNamespace(
                conf_uid="conf-1",
                character_name="Baoqiao",
                avatar="baoqiao.png",
            ),
        ),
    )
    current_conversation_tasks: dict[str, asyncio.Task[None] | None] = {"client-1": task}

    try:
        await cast("Any", conversation_handler).handle_individual_interrupt(
            "client-1",
            current_conversation_tasks,
            context,
            "",
        )
    finally:
        await asyncio.gather(task, return_exceptions=True)

    assert recorded_calls == [
        {
            "conf_uid": "conf-1",
            "history_uid": "history-1",
            "role": "system",
            "content": "[Interrupted by user]",
        }
    ]


@pytest.mark.anyio
async def test_handle_individual_interrupt_waits_for_task_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_finished = asyncio.Event()

    async def fake_turn() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            await asyncio.sleep(0)
            cleanup_finished.set()
            raise

    monkeypatch.setattr("lab.conversations.conversation_handler.store_message", lambda **kwargs: None)

    task: asyncio.Task[None] = asyncio.create_task(fake_turn())
    context = cast(
        "ServiceContext",
        SimpleNamespace(
            history_uid="history-1",
            character_config=SimpleNamespace(
                conf_uid="conf-1",
                character_name="Baoqiao",
                avatar="baoqiao.png",
            ),
        ),
    )
    current_conversation_tasks: dict[str, asyncio.Task[None] | None] = {"client-1": task}
    await asyncio.sleep(0)

    await cast("Any", conversation_handler).handle_individual_interrupt(
        "client-1",
        current_conversation_tasks,
        context,
        "",
    )

    assert cleanup_finished.is_set()
    assert task.done()
    assert "client-1" not in current_conversation_tasks


@pytest.mark.anyio
async def test_handle_conversation_trigger_cancels_existing_turn_before_starting_new_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_cleanup_finished = asyncio.Event()
    new_turn_started = asyncio.Event()

    async def fake_previous_turn() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            await asyncio.sleep(0)
            previous_cleanup_finished.set()
            raise

    async def fake_process_single_conversation(**kwargs: object) -> str:
        assert previous_cleanup_finished.is_set()
        new_turn_started.set()
        return str(kwargs["user_input"])

    class _FakeWebSocket:
        sent_messages: list[str]

        def __init__(self) -> None:
            self.sent_messages = []

        async def send_text(self, payload: str) -> None:
            self.sent_messages.append(payload)

    websocket = _FakeWebSocket()
    received_data_buffers = {"client-1": cast("Any", [])}
    current_conversation_tasks: dict[str, asyncio.Task[object] | None] = {
        "client-1": asyncio.create_task(fake_previous_turn())
    }
    await asyncio.sleep(0)

    monkeypatch.setattr(
        "lab.conversations.conversation_handler.process_single_conversation",
        fake_process_single_conversation,
    )

    context = cast("ServiceContext", SimpleNamespace())

    await cast("Any", conversation_handler).handle_conversation_trigger(
        "text-input",
        {"type": "text-input", "text": "你好"},
        "client-1",
        context,
        cast("Any", websocket),
        cast("Any", received_data_buffers),
        cast("Any", current_conversation_tasks),
    )
    await asyncio.sleep(0)

    assert new_turn_started.is_set()
    active_task = current_conversation_tasks.get("client-1")
    assert active_task is not None
    await asyncio.gather(active_task, return_exceptions=True)
    assert "client-1" not in current_conversation_tasks


def test_set_memory_from_history_skips_empty_assistant_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure loading legacy history ignores empty assistant entries."""

    def fake_get_history(conf_uid: str, history_uid: str) -> list[dict[str, str]]:
        del conf_uid, history_uid
        return [
            {"role": "user", "timestamp": "2026-03-21T00:00:00", "content": "hello"},
            {"role": "assistant", "timestamp": "2026-03-21T00:00:01", "content": ""},
            {"role": "system", "timestamp": "2026-03-21T00:00:02", "content": "[Interrupted by user]"},
            {"role": "assistant", "timestamp": "2026-03-21T00:00:03", "content": "let's continue"},
        ]

    monkeypatch.setattr("lab.agent.agents.memory_agent.memory_store.get_history", fake_get_history)

    store = MemoryStore()
    store.set_memory_from_history("conf-1", "history-1")

    messages = store.messages

    assert [(message.role, message.content) for message in messages] == [
        ("user", "hello"),
        ("assistant", "let's continue"),
    ]

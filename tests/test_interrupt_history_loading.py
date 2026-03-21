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

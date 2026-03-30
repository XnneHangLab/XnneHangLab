from __future__ import annotations

import asyncio

from lab.message_handler import MessageHandler


def test_message_handler_supports_multiple_waiters_for_same_message_type() -> None:
    async def run_test() -> None:
        handler = MessageHandler()

        first_waiter = asyncio.create_task(
            handler.wait_for_response(
                "client-1",
                "frontend-playback-complete",
                timeout=1.0,
                response_filter=lambda message: message.get("turn_id") == "turn-1",
            )
        )
        second_waiter = asyncio.create_task(
            handler.wait_for_response(
                "client-1",
                "frontend-playback-complete",
                timeout=1.0,
                response_filter=lambda message: message.get("turn_id") == "turn-2",
            )
        )

        await asyncio.sleep(0)
        handler.handle_message("client-1", {"type": "frontend-playback-complete", "turn_id": "turn-2"})
        handler.handle_message("client-1", {"type": "frontend-playback-complete", "turn_id": "turn-1"})

        first_result, second_result = await asyncio.gather(first_waiter, second_waiter)

        assert first_result == {"type": "frontend-playback-complete", "turn_id": "turn-1"}
        assert second_result == {"type": "frontend-playback-complete", "turn_id": "turn-2"}

    asyncio.run(run_test())


def test_message_handler_replays_early_message_to_later_waiter() -> None:
    async def run_test() -> None:
        handler = MessageHandler()
        handler.handle_message("client-1", {"type": "frontend-playback-complete", "turn_id": "turn-1"})

        result = await handler.wait_for_response(
            "client-1",
            "frontend-playback-complete",
            timeout=1.0,
            response_filter=lambda message: message.get("turn_id") == "turn-1",
        )

        assert result == {"type": "frontend-playback-complete", "turn_id": "turn-1"}

    asyncio.run(run_test())


def test_message_handler_does_not_replay_early_interrupt_signal() -> None:
    async def run_test() -> None:
        handler = MessageHandler()
        handler.handle_message("client-1", {"type": "interrupt-signal"})

        result = await handler.wait_for_response(
            "client-1",
            "interrupt-signal",
            timeout=0.01,
        )

        assert result is None

    asyncio.run(run_test())

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from lab.plugins.mood_chat import MoodChatPlugin


def test_mood_chat_cancels_timer_on_user_turn_and_rearms_after_turn() -> None:
    MoodChatPlugin._instance_count = 0
    plugin = MoodChatPlugin(initial_mood=90, interval_excited_s=5.0)

    async def _run() -> None:
        ctx = SimpleNamespace(extra={"agent": object()})
        try:
            await plugin._ensure_started(ctx)
            plugin._arm_proactive_timer()
            assert plugin._proactive_timer_task is not None

            await plugin.on_before_turn("hello", ctx)
            assert plugin._proactive_timer_task is None

            await plugin.on_after_turn("hello", "hi", ctx)
            assert plugin._proactive_timer_task is None

            await plugin.on_after_playback("hello", "hi", ctx)
            assert plugin._proactive_timer_task is not None
        finally:
            await plugin.stop()

    asyncio.run(_run())

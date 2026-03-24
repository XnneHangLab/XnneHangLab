# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
from pathlib import Path

from lab.plugins.mood_chat import MoodChatPlugin
from lab.tools.types import AgentContext


def test_mood_chat_cancels_timer_on_user_turn_and_rearms_after_turn() -> None:
    MoodChatPlugin._instance_count = 0
    plugin = MoodChatPlugin(initial_mood=90, interval_excited_s=5.0)

    async def _run() -> None:
        ctx = AgentContext(workspace_root=Path.cwd(), extra={"agent": object()})
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

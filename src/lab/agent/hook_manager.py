from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab.plugin.hook import HookPlugin
    from lab.tools.types import AgentContext


class HookManager:
    def __init__(self) -> None:
        self._hooks: list[HookPlugin] = []

    def register(self, hook: HookPlugin) -> None:
        self._hooks.append(hook)

    async def before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        """Collect hook results in registration order."""
        results: list[str] = []
        for hook in self._hooks:
            result = await hook.on_before_turn(user_text, ctx)
            if result:
                results.append(result)
        return "\n\n".join(results) if results else None

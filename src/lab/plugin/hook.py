from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab.tools.types import AgentContext


class HookPlugin(ABC):
    """Lifecycle hook plugin base class."""

    @abstractmethod
    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        """Run before a turn starts and optionally return memory context."""
        ...

    async def on_after_turn(self, user_text: str, assistant_text: str, ctx: AgentContext) -> None:
        """Run after text generation for a turn completes."""
        return

    async def on_after_playback(self, user_text: str, assistant_text: str, ctx: AgentContext) -> None:
        """Run after the turn's frontend playback has fully completed."""
        return

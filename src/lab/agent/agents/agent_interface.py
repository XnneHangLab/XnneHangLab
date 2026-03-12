from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from lab.agent.input_types import BaseInput
    from lab.agent.output_types import BaseOutput


class AgentInterface(ABC):
    """Base interface for all agent implementations."""

    @abstractmethod
    async def chat(self, input_data: BaseInput) -> AsyncIterator[BaseOutput]:
        """Chat with the agent asynchronously."""
        logger.critical("Agent: No chat function set.")
        raise ValueError("Agent: No chat function set.")

    @abstractmethod
    def handle_interrupt(self, heard_response: str) -> None:
        """Handle user interruption."""
        logger.warning("Agent: No interrupt handler set. The agent may not handle interruptions correctly.")

    @abstractmethod
    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """Load the agent's working memory from chat history."""
        raise NotImplementedError

    async def connect_mcp_servers(self, servers: list[tuple[str, str]] | None = None) -> None:  # noqa: B027
        """Connect MCP servers. Override in subclasses that support MCP."""

    async def close(self) -> None:  # noqa: B027
        """Release resources. Override in subclasses that hold connections."""

"""memory_agent package

Export the public MemoryAgent entrypoint.

Import path stability:
    from lab.agent.agents.memory_agent import MemoryAgent
"""

from __future__ import annotations

from .agent import MemoryAgent

__all__ = ["MemoryAgent"]

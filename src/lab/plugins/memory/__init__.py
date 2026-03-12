from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from lab.plugin.hook import HookPlugin

if TYPE_CHECKING:
    from lab.tools.types import AgentContext


class MemoryPlugin(HookPlugin):
    _requires_package = "memory_bench"

    def __init__(
        self,
        base_url: str = "http://localhost:12393",
        user_id: str = "xnne",
        agent_id: str = "congyin",
        search_limit: int = 10,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_id = user_id
        self._agent_id = agent_id
        self._search_limit = search_limit

    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                resp = await client.post(
                    f"{self._base_url}/memory/search",
                    json={
                        "query": user_text,
                        "user_id": self._user_id,
                        "agent_id": self._agent_id,
                        "limit": self._search_limit,
                    },
                )
                resp.raise_for_status()
                payload = resp.json()
                memories = payload.get("results", []) if isinstance(payload, dict) else []
                if not isinstance(memories, list) or not memories:
                    return None
                lines = [
                    memory.get("memory", "")
                    for memory in memories
                    if isinstance(memory, dict) and memory.get("memory")
                ]
                return "\n".join(lines) if lines else None
        except Exception:
            return None

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, TypedDict, cast

import httpx
from pydantic import Field

from lab.plugin.config import PluginConfigModel
from lab.plugin.hook import HookPlugin

if TYPE_CHECKING:
    from lab.tools.types import AgentContext


class _MemorySearchItem(TypedDict, total=False):
    memory: str


class MemoryPluginConfig(PluginConfigModel):
    base_url: Annotated[str, Field("http://localhost:12393", description="Memory Bench 服务基础地址")]
    user_id: Annotated[str, Field("xnne", description="记忆读写使用的用户 ID")]
    agent_id: Annotated[str, Field("congyin", description="记忆读写使用的角色 ID")]
    search_limit: Annotated[int, Field(10, ge=1, le=100, description="每轮注入的最大记忆条数")]


PLUGIN_CONFIG_MODEL = MemoryPluginConfig


class MemoryPlugin(HookPlugin):
    _requires_package = "memory_bench"
    config_model = MemoryPluginConfig

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
                payload = cast("dict[str, Any]", resp.json())
                raw_results = cast("list[Any]", payload.get("results", []))
                if not raw_results:
                    return None
                memories: list[_MemorySearchItem] = []
                for item in raw_results:
                    if isinstance(item, dict):
                        memories.append(cast("_MemorySearchItem", item))
                lines = [memory.get("memory", "") for memory in memories if memory.get("memory")]
                return "\n".join(lines) if lines else None
        except Exception:
            return None

    async def on_after_turn(self, user_text: str, assistant_text: str, ctx: AgentContext) -> None:
        del ctx
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.post(
                    f"{self._base_url}/memory/add",
                    json={
                        "user_text": user_text,
                        "assistant_text": assistant_text,
                        "user_id": self._user_id,
                        "agent_id": self._agent_id,
                    },
                )
                resp.raise_for_status()
        except Exception:
            pass

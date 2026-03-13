from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class MemoryBenchSettings(BaseModel):
    """Configuration for the memory_bench backend service."""

    user_id: Annotated[str, Field("xnne", title="mem0 User ID")]
    agent_id: Annotated[str, Field("congyin", title="mem0 Agent ID")]
    search_limit: Annotated[int, Field(10, ge=1, title="Default search limit")]
    server_api_key: Annotated[str, Field("", title="memory_bench API key (empty = disabled)")]

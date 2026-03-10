"""memory_bench 插件配置。

当 package.memory_bench = true 时，从 lab.toml 的 [memory_bench] 块读取配置。

LLM 配置直接复用 agent.chat_model，embedding 复用 agent.embedding，
此处只配置 memory_bench 自身的检索行为参数。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class MemoryBenchSettings(BaseModel):
    """memory_bench 插件配置。放在 lab.toml 的 [memory_bench] 块下。"""

    user_id: Annotated[str, Field("xnne", title="mem0 用户 ID")]
    agent_id: Annotated[str, Field("congyin", title="mem0 Agent ID")]
    search_limit: Annotated[int, Field(10, ge=1, title="每次召回的最大记忆条数")]
    server_api_key: Annotated[str, Field("", title="proxy_router 鉴权 Key（空=不鉴权）")]

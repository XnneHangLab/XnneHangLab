"""memory_bench 插件配置。

当 package.memory_bench = true 时，从 lab.toml 的 [memory_bench] 块读取配置。

LLM 配置：
- proxy 上游转发目标由 upstream_llm_provider 显式指定（不能复用 chat_model.llm_provider，
  因为 chat_model 此时指向 memory_bench 自身，直接读会回环）
- mem0 事实提取 LLM 复用同一个 upstream_llm_provider
- embedding 复用 agent.embedding
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from lab.config_manager.agent import LLM_Provider


class MemoryBenchSettings(BaseModel):
    """memory_bench 插件配置。放在 lab.toml 的 [memory_bench] 块下。"""

    upstream_llm_provider: Annotated[
        LLM_Provider,
        Field("oaipro", title="proxy 上游真实 LLM provider（不能填 memory_bench，否则回环）"),
    ]
    user_id: Annotated[str, Field("xnne", title="mem0 用户 ID")]
    agent_id: Annotated[str, Field("congyin", title="mem0 Agent ID")]
    search_limit: Annotated[int, Field(10, ge=1, title="每次召回的最大记忆条数")]
    server_api_key: Annotated[str, Field("", title="proxy_router 鉴权 Key（空=不鉴权）")]

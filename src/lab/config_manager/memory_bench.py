"""memory_bench 插件配置。

当 package.memory_bench = true 时，从 lab.toml 的 [memory_bench] 块读取配置，
通过 overrides 传入 resolve_memory_bench_config()，优先级高于 .env.benchmark。

字段说明：
- llm_*        : mem0 使用的 LLM（用于事实提取）。不填时自动复用 chat_model 配置。
- embedding_*  : 向量嵌入模型（必填，mem0 向量存储依赖）。
- user_id / agent_id / search_limit : mem0 检索参数。
- server_api_key : proxy_router 的鉴权 key，空字符串表示不鉴权。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class MemoryBenchEmbeddingSettings(BaseModel):
    """向量嵌入模型配置（mem0 必须）。"""

    api_key: Annotated[str, Field("", title="Embedding API Key")]
    base_url: Annotated[str, Field("https://api.oaipro.com/v1", title="Embedding Base URL")]
    model: Annotated[str, Field("text-embedding-3-small", title="Embedding Model Name")]


class MemoryBenchLLMSettings(BaseModel):
    """mem0 事实提取 LLM 配置。

    留空时 resolve_memory_bench_config() 会自动 fallback 到 chat_model 的配置。
    """

    api_key: Annotated[str, Field("", title="mem0 LLM API Key（空=复用 chat_model）")]
    base_url: Annotated[str, Field("", title="mem0 LLM Base URL（空=复用 chat_model）")]
    model: Annotated[str, Field("", title="mem0 LLM Model Name（空=复用 chat_model）")]


class MemoryBenchSettings(BaseModel):
    """memory_bench 插件完整配置。

    放在 lab.toml 的 [memory_bench] 块下。
    """

    user_id: Annotated[str, Field("xnne", title="mem0 用户 ID")]
    agent_id: Annotated[str, Field("congyin", title="mem0 Agent ID")]
    search_limit: Annotated[int, Field(10, ge=1, title="每次召回的最大记忆条数")]
    server_api_key: Annotated[str, Field("", title="proxy_router 鉴权 Key（空=不鉴权）")]

    embedding: Annotated[
        MemoryBenchEmbeddingSettings,
        Field(MemoryBenchEmbeddingSettings()),  # pyright: ignore[reportCallIssue]
    ]
    llm: Annotated[
        MemoryBenchLLMSettings,
        Field(MemoryBenchLLMSettings()),  # pyright: ignore[reportCallIssue]
    ]

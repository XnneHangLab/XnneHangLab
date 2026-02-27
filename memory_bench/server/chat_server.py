#!/usr/bin/env python3
"""Memory Chat Server — standalone launcher for the memory-augmented chat router.

This file handles:
- CLI argument parsing
- Environment variable loading (.env.benchmark)
- mem0 + OpenAI client initialization
- FastAPI app assembly (mounting the router)
- uvicorn startup

The actual request handling lives in ``router.py`` and can be mounted
independently into any FastAPI application.

Usage::

    uv run memory_bench/server/chat_server.py \\
        --chat-api-key sk-xxx \\
        --chat-base-url https://openrouter.ai/api/v1 \\
        --chat-model google/gemini-2.0-flash \\
        --port 8080

    # Or rely on memory_bench/.env.benchmark:
    uv run memory_bench/server/chat_server.py
"""

from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from openai import OpenAI

from memory_bench.scripts.bench_logger import logger
from memory_bench.server.router import router, state as router_state

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_STATE_DIR = _REPO_ROOT / "memory_bench" / "state"
_DOTENV_BENCHMARK_PATH = _REPO_ROOT / "memory_bench" / ".env.benchmark"

_DEFAULT_SEARCH_LIMIT = 10
_DEFAULT_USER_ID = "xnne"
_DEFAULT_AGENT_ID = "congyin"

# Custom fact extraction prompt — extract facts about BOTH user and AI assistant.
# Output in Chinese with clear prefixes to distinguish ownership.
_FACT_EXTRACTION_PROMPT = """你是一个事实提取器。你的任务是从对话中提取关于**用户**和**AI 助手**的事实。

输入：一段用户与 AI 助手之间的对话。

## 关键规则

1. **提取用户的事实**（关于说话的人）：
   - 偏好（喜欢/不喜欢什么）
   - 经历（做过什么事、去过哪里）
   - 习惯（日常行为）
   - 关系（家人、朋友、同事）
   - 知识/技能（会什么、懂什么）
   - 观点/信念（怎么想、重视什么）
   - 计划/目标（想做什么）

2. **提取 AI 助手的事实**（关于 AI 自己的描述）：
   - AI 的名字/身份
   - AI 的性格特点
   - AI 的能力/限制
   - AI 的偏好（如果 AI 表达了）
   - AI 的背景故事（如果有）

3. **输出格式**：每条事实必须加前缀
   - `[User]` 开头 = 关于用户的事实
   - `[Agent]` 开头 = 关于 AI 助手的事实

4. **语言**：所有事实必须用**中文**输出

## 示例

用户："我叫 xnne，喜欢打篮球。"
→ 提取：["[User] 用户的名字是 xnne。", "[User] 用户喜欢打篮球。"]

AI："我是聪音，性格有点内向。"
→ 提取：["[Agent] AI 的名字是聪音。", "[Agent] AI 性格内向。"]

用户："今天天气不错" / AI："是啊，适合出门"
→ 提取：[]（没有持久性事实）

## 输出格式（JSON）

{
  "facts": ["[User/Agent] 事实 1", "[User/Agent] 事实 2", ...]
}

如果没有发现任何事实，返回：{"facts": []}"""


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------


def _load_dotenv() -> None:
    """Load memory_bench/.env.benchmark if present."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"):
        os.environ.pop(key, None)

    if _DOTENV_BENCHMARK_PATH.exists():
        load_dotenv(dotenv_path=_DOTENV_BENCHMARK_PATH, override=True)


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "")
    return value if value.strip() else default


# ---------------------------------------------------------------------------
# Mem0 initialization (mirrors replay_mem0.py)
# ---------------------------------------------------------------------------


def _build_mem0_config(
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str,
    embedding_api_key: str,
    embedding_base_url: str,
    embedding_model: str,
) -> dict[str, Any]:
    qdrant_path = _STATE_DIR / "qdrant_storage"
    qdrant_path.mkdir(parents=True, exist_ok=True)
    return {
        "llm": {
            "provider": "openai",
            "config": {
                "api_key": llm_api_key,
                "openai_base_url": llm_base_url,
                "model": llm_model,
                "temperature": 0.0,
                "max_tokens": 2000,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": embedding_api_key,
                "openai_base_url": embedding_base_url,
                "model": embedding_model,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "memory_bench_global",
                "path": str(qdrant_path),
                "on_disk": True,
            },
        },
        "custom_fact_extraction_prompt": _FACT_EXTRACTION_PROMPT,
    }


def _init_mem0(
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str,
    embedding_api_key: str,
    embedding_base_url: str,
    embedding_model: str,
) -> Any:
    from mem0 import Memory

    config = _build_mem0_config(
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        embedding_api_key=embedding_api_key,
        embedding_base_url=embedding_base_url,
        embedding_model=embedding_model,
    )
    memory = Memory.from_config(config)

    # WORKAROUND: mem0 vector=None bug → use set_payload instead of update.
    vector_store = getattr(memory, "vector_store", None)
    original_update = getattr(vector_store, "update", None)
    if callable(original_update):

        def _patched_update(
            vector_id: str,
            vector: Any = None,
            payload: dict[str, Any] | None = None,
        ) -> None:
            if vector is None:
                client = getattr(vector_store, "client", None)
                if client is not None and hasattr(client, "set_payload"):
                    collection_name = getattr(memory, "collection_name", None) or getattr(
                        vector_store, "collection_name", None
                    )
                    if collection_name and payload:
                        from qdrant_client.models import PointIdsList

                        client.set_payload(
                            collection_name=collection_name,
                            payload=payload,
                            points=PointIdsList(points=[vector_id]),
                        )
                        return
            original_update(vector_id, vector=vector, payload=payload)

        vector_store.update = _patched_update

    return memory


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def _resolve_config(args: argparse.Namespace) -> dict[str, Any]:
    """Merge CLI args + env vars.  CLI wins."""

    def resolve(cli_val: str | None, env_name: str, default: str | None = None) -> str:
        val = cli_val or _get_env(env_name) or default
        if not val:
            msg = f"Missing required config: --{env_name.lower().replace('_', '-')} or {env_name}"
            raise RuntimeError(msg)
        return val

    chat_api_key = resolve(args.chat_api_key, "CHAT_API_KEY", _get_env("BENCHMARK_LLM_API_KEY"))
    chat_base_url = resolve(args.chat_base_url, "CHAT_BASE_URL", _get_env("BENCHMARK_LLM_BASE_URL"))
    chat_model = resolve(args.chat_model, "CHAT_MODEL", _get_env("BENCHMARK_LLM_MODEL"))

    llm_api_key = resolve(args.mem0_llm_api_key, "MEM0_LLM_API_KEY", chat_api_key)
    llm_base_url = resolve(args.mem0_llm_base_url, "MEM0_LLM_BASE_URL", chat_base_url)
    llm_model = resolve(args.mem0_llm_model, "MEM0_LLM_MODEL", chat_model)

    embedding_api_key = resolve(args.embedding_api_key, "BENCHMARK_EMBEDDING_API_KEY")
    embedding_base_url = resolve(args.embedding_base_url, "BENCHMARK_EMBEDDING_BASE_URL")
    embedding_model = resolve(args.embedding_model, "BENCHMARK_EMBEDDING_MODEL")

    # Claim LLM config (for graph pipeline) — falls back to mem0 LLM, then chat LLM
    claim_api_key = args.claim_llm_api_key or _get_env("CLAIM_LLM_API_KEY") or llm_api_key
    claim_base_url = args.claim_llm_base_url or _get_env("CLAIM_LLM_BASE_URL") or llm_base_url
    claim_model = args.claim_llm_model or _get_env("CLAIM_LLM_MODEL") or llm_model

    # Neo4j config
    neo4j_container = args.neo4j_container or _get_env("NEO4J_CONTAINER", "membench-neo4j-mem0")
    neo4j_user = args.neo4j_user or _get_env("NEO4J_USER", "neo4j")
    neo4j_password = args.neo4j_password or _get_env("NEO4J_PASSWORD", "neo4jneo4j")

    return {
        "chat_api_key": chat_api_key,
        "chat_base_url": chat_base_url,
        "chat_model": chat_model,
        "llm_api_key": llm_api_key,
        "llm_base_url": llm_base_url,
        "llm_model": llm_model,
        "embedding_api_key": embedding_api_key,
        "embedding_base_url": embedding_base_url,
        "embedding_model": embedding_model,
        "user_id": args.user_id or _get_env("CHAT_USER_ID", _DEFAULT_USER_ID),
        "agent_id": args.agent_id or _get_env("CHAT_AGENT_ID", _DEFAULT_AGENT_ID),
        "search_limit": args.search_limit,
        "server_api_key": args.server_api_key or _get_env("CHAT_SERVER_API_KEY") or None,
        "port": args.port,
        "host": args.host,
        # Graph pipeline
        "claim_api_key": claim_api_key,
        "claim_base_url": claim_base_url,
        "claim_model": claim_model,
        "neo4j_container": neo4j_container,
        "neo4j_user": neo4j_user,
        "neo4j_password": neo4j_password,
        "enable_graph": args.enable_graph,
        # Metadata nodes
        "metadata_user_id": args.metadata_user_id or _get_env("METADATA_USER_ID", "xnne"),
        "metadata_user_name": args.metadata_user_name or _get_env("METADATA_USER_NAME", "xnne"),
        "metadata_agent_id": args.metadata_agent_id or _get_env("METADATA_AGENT_ID", "congyin"),
        "metadata_agent_name": args.metadata_agent_name or _get_env("METADATA_AGENT_NAME", "congyin"),
        "metadata_scene_id": args.metadata_scene_id or _get_env("METADATA_SCENE_ID", "chill_ai_chat"),
        "metadata_scene_name": args.metadata_scene_name or _get_env("METADATA_SCENE_NAME", "Chill AI Chat"),
        "metadata_character_id": args.metadata_character_id or _get_env("METADATA_CHARACTER_ID", "congyin"),
        "metadata_character_name": args.metadata_character_name or _get_env("METADATA_CHARACTER_NAME", "聪音 (Congyin)"),
    }


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise mem0 + OpenAI client, populate router state."""
    _load_dotenv()
    cfg = _resolve_config(_parse_args())

    # mem0
    try:
        router_state.mem0 = _init_mem0(
            llm_api_key=cfg["llm_api_key"],
            llm_base_url=cfg["llm_base_url"],
            llm_model=cfg["llm_model"],
            embedding_api_key=cfg["embedding_api_key"],
            embedding_base_url=cfg["embedding_base_url"],
            embedding_model=cfg["embedding_model"],
        )
        logger.info("\u2705 mem0 initialized (qdrant: %s)", _STATE_DIR / "qdrant_storage")
    except Exception as exc:
        logger.warning("\u26a0\ufe0f mem0 init failed: %s — server will run without memory", exc)

    # OpenAI forwarding client
    router_state.openai_client = OpenAI(api_key=cfg["chat_api_key"], base_url=cfg["chat_base_url"])
    router_state.chat_model = cfg["chat_model"]
    router_state.user_id = cfg["user_id"]
    router_state.agent_id = cfg["agent_id"]
    router_state.search_limit = cfg["search_limit"]
    router_state.api_key = cfg["server_api_key"]

    logger.info("\u2705 LLM proxy: %s / %s", cfg["chat_base_url"], cfg["chat_model"])
    if cfg["server_api_key"]:
        logger.info("\u2705 API key auth enabled")
    else:
        logger.warning("\u26a0\ufe0f No CHAT_SERVER_API_KEY set — server is open (no auth)")

    # Graph pipeline (claim extraction + Neo4j write)
    if cfg["enable_graph"]:
        router_state.claim_llm_client = OpenAI(
            api_key=cfg["claim_api_key"],
            base_url=cfg["claim_base_url"],
        )
        router_state.claim_llm_model = cfg["claim_model"]
        router_state.neo4j_container = cfg["neo4j_container"]
        router_state.neo4j_user = cfg["neo4j_user"]
        router_state.neo4j_password = cfg["neo4j_password"]
        router_state.graph_pipeline_enabled = True
        # Metadata nodes
        router_state.metadata_user_id = cfg["metadata_user_id"]
        router_state.metadata_user_name = cfg["metadata_user_name"]
        router_state.metadata_agent_id = cfg["metadata_agent_id"]
        router_state.metadata_agent_name = cfg["metadata_agent_name"]
        router_state.metadata_scene_id = cfg["metadata_scene_id"]
        router_state.metadata_scene_name = cfg["metadata_scene_name"]
        router_state.metadata_character_id = cfg["metadata_character_id"]
        router_state.metadata_character_name = cfg["metadata_character_name"]
        logger.info(
            "\u2705 Graph pipeline enabled: claim LLM=%s/%s, Neo4j=%s",
            cfg["claim_base_url"],
            cfg["claim_model"],
            cfg["neo4j_container"],
        )
        # Initialize metadata nodes
        from memory_bench.server.router import init_metadata_nodes
        init_metadata_nodes()
    else:
        logger.info("\u2139\ufe0f Graph pipeline disabled (use --enable-graph to enable)")

    logger.info("\u2705 Listening on %s:%s", cfg["host"], cfg["port"])

    yield


# ---------------------------------------------------------------------------
# App assembly
# ---------------------------------------------------------------------------

app = FastAPI(title="Memory Chat Server", lifespan=lifespan)
app.include_router(router)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Memory Chat Server — OpenAI-compatible proxy with mem0")

    p.add_argument("--chat-api-key", default=None, help="API key for the chat LLM provider")
    p.add_argument("--chat-base-url", default=None, help="Base URL for the chat LLM provider")
    p.add_argument("--chat-model", default=None, help="Model name for chat completions")

    p.add_argument("--mem0-llm-api-key", default=None, help="API key for mem0 LLM (default: same as chat)")
    p.add_argument("--mem0-llm-base-url", default=None, help="Base URL for mem0 LLM (default: same as chat)")
    p.add_argument("--mem0-llm-model", default=None, help="Model for mem0 LLM (default: same as chat)")

    p.add_argument("--embedding-api-key", default=None, help="API key for embedding model")
    p.add_argument("--embedding-base-url", default=None, help="Base URL for embedding model")
    p.add_argument("--embedding-model", default=None, help="Embedding model name")

    p.add_argument("--user-id", default=None, help=f"User ID for mem0 (default: {_DEFAULT_USER_ID})")
    p.add_argument("--agent-id", default=None, help=f"Agent ID for mem0 (default: {_DEFAULT_AGENT_ID})")

    p.add_argument(
        "--server-api-key", default=None, help="API key for server auth (env: CHAT_SERVER_API_KEY). If unset, no auth."
    )
    p.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    p.add_argument("--host", default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    p.add_argument("--search-limit", type=int, default=_DEFAULT_SEARCH_LIMIT, help="Max memories per request")

    # Graph pipeline (claim extraction + Neo4j)
    p.add_argument(
        "--enable-graph", action="store_true", help="Enable realtime graph pipeline (claim extraction + Neo4j write)"
    )
    p.add_argument(
        "--claim-llm-api-key", default=None, help="API key for claim extraction LLM (default: same as mem0 LLM)"
    )
    p.add_argument(
        "--claim-llm-base-url", default=None, help="Base URL for claim extraction LLM (default: same as mem0 LLM)"
    )
    p.add_argument("--claim-llm-model", default=None, help="Model for claim extraction LLM (default: same as mem0 LLM)")
    p.add_argument("--neo4j-container", default=None, help="Neo4j Docker container name (default: membench-neo4j-mem0)")
    p.add_argument("--neo4j-user", default=None, help="Neo4j username (default: neo4j)")
    p.add_argument("--neo4j-password", default=None, help="Neo4j password (default: neo4jneo4j)")
    # Metadata nodes
    p.add_argument("--metadata-user-id", default=None, help="User ID for metadata nodes (default: xnne)")
    p.add_argument("--metadata-user-name", default=None, help="User name for metadata nodes (default: xnne)")
    p.add_argument("--metadata-agent-id", default=None, help="Agent ID for metadata nodes (default: congyin)")
    p.add_argument("--metadata-agent-name", default=None, help="Agent name for metadata nodes (default: congyin)")
    p.add_argument("--metadata-scene-id", default=None, help="Scene ID for metadata nodes (default: chill_ai_chat)")
    p.add_argument("--metadata-scene-name", default=None, help="Scene name for metadata nodes (default: Chill AI Chat)")
    p.add_argument("--metadata-character-id", default=None, help="Character ID for metadata nodes (default: congyin)")
    p.add_argument("--metadata-character-name", default=None, help="Character name for metadata nodes (default: 聪音 (Congyin))")
    return p


def _parse_args() -> argparse.Namespace:
    return _build_parser().parse_args()


def main() -> None:
    """CLI entrypoint."""
    _load_dotenv()
    args = _parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

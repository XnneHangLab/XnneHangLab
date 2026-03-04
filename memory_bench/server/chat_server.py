#!/usr/bin/env python3
"""Memory Chat Server — standalone launcher for the memory-augmented chat router.

This file handles:
- CLI argument parsing
- Environment variable loading (.env.benchmark)
- FastAPI app assembly (mounting the router)
- uvicorn startup

Initialisation logic (mem0, OpenAI client, graph pipeline) lives in
``startup.py`` so that the same setup can be reused when the router is
mounted into an external FastAPI application (e.g. the main XnneHangLab
server).

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
from contextlib import asynccontextmanager

import uvicorn  # type: ignore[reportMissingImports,reportUnknownVariableType]
from fastapi import FastAPI  # type: ignore[reportMissingImports,reportUnknownVariableType]

from memory_bench.scripts.bench_logger import logger
from memory_bench.server.chat_router import chat_state, router as chat_router
from memory_bench.server.router import router, state as router_state
from memory_bench.server.startup import (
    init_chat_router_state,
    init_router_state,
    load_memory_bench_env,
    resolve_memory_bench_config,
)

_DEFAULT_SEARCH_LIMIT = 10
_DEFAULT_USER_ID = "xnne"
_DEFAULT_AGENT_ID = "congyin"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[reportUnknownParameterType]
    """Initialise mem0 + OpenAI client, populate router state."""
    load_memory_bench_env()
    args = _parse_args()
    cfg = resolve_memory_bench_config(
        overrides={
            "chat_api_key": args.chat_api_key,
            "chat_base_url": args.chat_base_url,
            "chat_model": args.chat_model,
            "llm_api_key": args.mem0_llm_api_key,
            "llm_base_url": args.mem0_llm_base_url,
            "llm_model": args.mem0_llm_model,
            "embedding_api_key": args.embedding_api_key,
            "embedding_base_url": args.embedding_base_url,
            "embedding_model": args.embedding_model,
            "user_id": args.user_id,
            "agent_id": args.agent_id,
            "search_limit": args.search_limit,
            "server_api_key": args.server_api_key,
            "port": args.port,
            "host": args.host,
            "enable_graph": args.enable_graph,
            "claim_api_key": args.claim_llm_api_key,
            "claim_base_url": args.claim_llm_base_url,
            "claim_model": args.claim_llm_model,
            "neo4j_container": args.neo4j_container,
            "neo4j_user": args.neo4j_user,
            "neo4j_password": args.neo4j_password,
            "metadata_user_id": args.metadata_user_id,
            "metadata_user_name": args.metadata_user_name,
            "metadata_agent_id": args.metadata_agent_id,
            "metadata_agent_name": args.metadata_agent_name,
            "metadata_scene_id": args.metadata_scene_id,
            "metadata_scene_name": args.metadata_scene_name,
            "metadata_character_id": args.metadata_character_id,
            "metadata_character_name": args.metadata_character_name,
        }
    )

    init_router_state(router_state, cfg)
    init_chat_router_state(chat_state, cfg)
    logger.info("✅ Listening on %s:%s", cfg["host"], cfg["port"])

    yield


# ---------------------------------------------------------------------------
# App assembly
# ---------------------------------------------------------------------------

app = FastAPI(title="Memory Chat Server", lifespan=lifespan)  # type: ignore[reportUnknownVariableType]
app.include_router(router)  # type: ignore[reportUnknownMemberType]
app.include_router(chat_router, prefix="/memory")  # type: ignore[reportUnknownMemberType]


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
    p.add_argument(
        "--metadata-character-name", default=None, help="Character name for metadata nodes (default: 聪音 (Congyin))"
    )
    return p


def _parse_args() -> argparse.Namespace:
    return _build_parser().parse_args()


def main() -> None:
    """CLI entrypoint."""
    load_memory_bench_env()
    args = _parse_args()
    uvicorn.run(app, host=args.host, port=args.port)  # type: ignore[reportUnknownMemberType]


if __name__ == "__main__":
    main()

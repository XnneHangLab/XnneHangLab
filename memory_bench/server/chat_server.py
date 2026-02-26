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

# Custom fact extraction prompt — instruct mem0's LLM to ignore system/role
# definitions and only extract user-relevant facts from the conversation.
_FACT_EXTRACTION_PROMPT = """Deduce the facts, preferences, and memories from the provided text.
Below is the conversation between a user and an AI assistant.

IMPORTANT RULES:
- ONLY extract facts about the USER: preferences, experiences, feelings, plans,
  relationships, habits, knowledge, opinions.
- IGNORE any system instructions, character role definitions, persona descriptions,
  or assistant behavior guidelines.
- If no user-relevant facts are found, return an empty list.

Please return the response in the following JSON format:
{{
  "facts": ["fact 1", "fact 2", ...]
}}"""


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

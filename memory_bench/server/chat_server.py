#!/usr/bin/env python3
"""Memory Chat Server — OpenAI-compatible `/v1/chat/completions` proxy with mem0 augmentation.

Architecture:
    AIChat Mod (C#)
        ↓  POST /v1/chat/completions
    Memory Chat Server (FastAPI)
        ├─ mem0.search() → recall relevant memories
        ├─ inject memories into system prompt
        ├─ forward to real LLM provider (OpenAI-compatible)
        ├─ async mem0.add() → store new conversation
        └─ return standard ChatCompletion response

Usage:
    uv run memory_bench/server/chat_server.py \\
        --chat-api-key sk-xxx \\
        --chat-base-url https://openrouter.ai/api/v1 \\
        --chat-model google/gemini-2.0-flash \\
        --embedding-api-key sk-xxx \\
        --embedding-base-url https://api.openai.com/v1 \\
        --embedding-model text-embedding-3-small \\
        --port 8080

    Or via environment variables in memory_bench/.env.server:
    uv run memory_bench/server/chat_server.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_STATE_DIR = _REPO_ROOT / "memory_bench" / "state"
_DOTENV_PATH = _REPO_ROOT / "memory_bench" / ".env.server"
_DOTENV_BENCHMARK_PATH = _REPO_ROOT / "memory_bench" / ".env.benchmark"

# Default memory search params
_DEFAULT_SEARCH_LIMIT = 10
_DEFAULT_USER_ID = "xnne"
_DEFAULT_AGENT_ID = "congyin"

# System prompt template for memory injection
_MEMORY_INJECTION_TEMPLATE = """## Recalled Memories
The following memories were recalled from previous conversations and may be relevant:

{memories}

---
Use these memories naturally in your response when relevant. Do not mention that you "recalled" or "retrieved" them."""


# ---------------------------------------------------------------------------
# Pydantic models (OpenAI-compatible request/response)
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: str
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stream: bool = False
    # Allow extra fields from AIChat Mod
    model_config = {"extra": "allow"}


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: list[ChatCompletionChoice]
    usage: UsageInfo = Field(default_factory=UsageInfo)


# ---------------------------------------------------------------------------
# Server state (initialized at startup)
# ---------------------------------------------------------------------------


class ServerState:
    """Holds initialized clients and config, set during lifespan startup."""

    mem0: Any = None
    openai_client: OpenAI | None = None
    chat_model: str = ""
    user_id: str = _DEFAULT_USER_ID
    agent_id: str = _DEFAULT_AGENT_ID
    search_limit: int = _DEFAULT_SEARCH_LIMIT


state = ServerState()


# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------


def _load_dotenv() -> None:
    """Load .env.server (preferred) or fall back to .env.benchmark."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    # Clear potentially conflicting global OpenAI env vars
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"):
        os.environ.pop(key, None)

    if _DOTENV_PATH.exists():
        load_dotenv(dotenv_path=_DOTENV_PATH, override=True)
    elif _DOTENV_BENCHMARK_PATH.exists():
        load_dotenv(dotenv_path=_DOTENV_BENCHMARK_PATH, override=True)


def _get_env(name: str, default: str | None = None) -> str | None:
    """Read env var, treating empty string as missing."""
    value = os.environ.get(name, "")
    return value if value.strip() else default


# ---------------------------------------------------------------------------
# Mem0 initialization (mirrors replay_mem0.py pattern)
# ---------------------------------------------------------------------------


def _build_mem0_config(
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str,
    embedding_api_key: str,
    embedding_base_url: str,
    embedding_model: str,
) -> dict[str, Any]:
    """Build mem0 config dict for Memory.from_config()."""
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
    }


def _init_mem0(
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str,
    embedding_api_key: str,
    embedding_base_url: str,
    embedding_model: str,
) -> Any:
    """Initialize mem0 Memory with monkey-patch for vector=None bug."""
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

    # WORKAROUND: mem0 bug - vector=None on NONE events causes qdrant ValidationError.
    # Patch vector_store.update to use set_payload when vector is None.
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
# Memory search & injection
# ---------------------------------------------------------------------------


def _search_memories(query: str) -> list[dict[str, Any]]:
    """Search mem0 for relevant memories given a query string."""
    if state.mem0 is None:
        return []
    try:
        results = state.mem0.search(
            query=query,
            user_id=state.user_id,
            agent_id=state.agent_id,
            limit=state.search_limit,
        )
        if isinstance(results, dict):
            return results.get("results", [])
        if isinstance(results, list):
            return results
    except Exception:
        # Don't fail the request if memory search fails
        pass
    return []


def _format_memories(memories: list[dict[str, Any]]) -> str:
    """Format memory search results into a readable string for prompt injection."""
    if not memories:
        return ""
    lines: list[str] = []
    for i, mem in enumerate(memories, 1):
        text = mem.get("memory", "") or mem.get("data", "") or str(mem)
        score = mem.get("score", "")
        score_str = f" (relevance: {score:.2f})" if isinstance(score, float) else ""
        lines.append(f"{i}. {text}{score_str}")
    return "\n".join(lines)


def _inject_memories_into_messages(
    messages: list[ChatMessage],
    memories_text: str,
) -> list[ChatMessage]:
    """Inject recalled memories into the message list via system prompt."""
    if not memories_text:
        return messages

    injection = _MEMORY_INJECTION_TEMPLATE.format(memories=memories_text)

    # If there's already a system message, append to it
    result = list(messages)
    for i, msg in enumerate(result):
        if msg.role == "system":
            result[i] = ChatMessage(
                role="system",
                content=msg.content + "\n\n" + injection,
            )
            return result

    # No system message — prepend one
    result.insert(0, ChatMessage(role="system", content=injection))
    return result


# ---------------------------------------------------------------------------
# Async memory write-back
# ---------------------------------------------------------------------------


def _add_memory_sync(user_msg: str, assistant_msg: str) -> None:
    """Synchronous mem0.add() — called from background thread."""
    if state.mem0 is None:
        return
    try:
        messages = [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
        state.mem0.add(
            messages=messages,
            user_id=state.user_id,
            agent_id=state.agent_id,
            metadata={
                "scene_id": "chill_ai_chat",
                "character_id": state.agent_id,
            },
        )
    except Exception:
        # Memory write failure should not affect the response
        pass


async def _add_memory_background(user_msg: str, assistant_msg: str) -> None:
    """Run mem0.add() in a background thread to avoid blocking the response."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _add_memory_sync, user_msg, assistant_msg)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize mem0 and OpenAI client at startup."""
    _load_dotenv()

    args = _parse_args_from_env()

    # Init mem0
    try:
        state.mem0 = _init_mem0(
            llm_api_key=args["llm_api_key"],
            llm_base_url=args["llm_base_url"],
            llm_model=args["llm_model"],
            embedding_api_key=args["embedding_api_key"],
            embedding_base_url=args["embedding_base_url"],
            embedding_model=args["embedding_model"],
        )
        print(f"✅ mem0 initialized (qdrant: {_STATE_DIR / 'qdrant_storage'})")
    except Exception as exc:
        print(f"⚠️ mem0 init failed: {exc} — server will run without memory")

    # Init OpenAI client for forwarding
    state.openai_client = OpenAI(
        api_key=args["chat_api_key"],
        base_url=args["chat_base_url"],
    )
    state.chat_model = args["chat_model"]
    state.user_id = args["user_id"]
    state.agent_id = args["agent_id"]
    state.search_limit = args["search_limit"]

    print(f"✅ LLM proxy: {args['chat_base_url']} / {args['chat_model']}")
    print(f"✅ Listening on port {args['port']}")

    yield


def _parse_args_from_env() -> dict[str, Any]:
    """Resolve config from CLI args + env vars. CLI wins over env."""
    parser = _build_parser()
    args = parser.parse_args()

    def resolve(cli_val: str | None, env_name: str, default: str | None = None) -> str:
        val = cli_val or _get_env(env_name) or default
        if not val:
            raise RuntimeError(f"Missing required config: --{env_name.lower().replace('_', '-')} or {env_name}")
        return val

    # Chat provider (for forwarding LLM calls) — separate from mem0's LLM
    chat_api_key = resolve(args.chat_api_key, "CHAT_API_KEY", _get_env("BENCHMARK_LLM_API_KEY"))
    chat_base_url = resolve(args.chat_base_url, "CHAT_BASE_URL", _get_env("BENCHMARK_LLM_BASE_URL"))
    chat_model = resolve(args.chat_model, "CHAT_MODEL", _get_env("BENCHMARK_LLM_MODEL"))

    # Mem0 LLM (for memory extraction) — can differ from chat provider
    llm_api_key = resolve(args.mem0_llm_api_key, "MEM0_LLM_API_KEY", chat_api_key)
    llm_base_url = resolve(args.mem0_llm_base_url, "MEM0_LLM_BASE_URL", chat_base_url)
    llm_model = resolve(args.mem0_llm_model, "MEM0_LLM_MODEL", chat_model)

    # Embedding
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
        "port": args.port,
    }


app = FastAPI(title="Memory Chat Server", lifespan=lifespan)


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> JSONResponse:
    """OpenAI-compatible chat completions endpoint with memory augmentation."""
    if state.openai_client is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    if request.stream:
        raise HTTPException(status_code=400, detail="Streaming is not supported yet")

    # 1. Extract the latest user message for memory search
    user_messages = [m for m in request.messages if m.role == "user"]
    latest_user_msg = user_messages[-1].content if user_messages else ""

    # 2. Search mem0 for relevant memories
    memories = _search_memories(latest_user_msg) if latest_user_msg else []
    memories_text = _format_memories(memories)

    # 3. Inject memories into messages
    augmented_messages = _inject_memories_into_messages(request.messages, memories_text)

    # 4. Forward to real LLM provider
    model = request.model or state.chat_model
    try:
        completion = state.openai_client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in augmented_messages],
            temperature=request.temperature if request.temperature is not None else 0.7,
            max_tokens=request.max_tokens or 2000,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {exc}") from exc

    # 5. Extract assistant response
    assistant_content = completion.choices[0].message.content or ""

    # 6. Async write-back to mem0 (fire and forget)
    if latest_user_msg and assistant_content:
        asyncio.create_task(_add_memory_background(latest_user_msg, assistant_content))

    # 7. Return standard ChatCompletion response
    response = ChatCompletionResponse(
        model=model,
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=assistant_content),
            )
        ],
        usage=UsageInfo(
            prompt_tokens=getattr(completion.usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(completion.usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(completion.usage, "total_tokens", 0) or 0,
        ),
    )
    return JSONResponse(content=json.loads(response.model_dump_json()))


@app.get("/v1/models")
async def list_models() -> JSONResponse:
    """Minimal /v1/models endpoint for compatibility."""
    return JSONResponse(
        content={
            "object": "list",
            "data": [
                {
                    "id": state.chat_model,
                    "object": "model",
                    "owned_by": "memory-chat-server",
                }
            ],
        }
    )


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        content={
            "status": "ok",
            "mem0_ready": state.mem0 is not None,
            "llm_ready": state.openai_client is not None,
            "model": state.chat_model,
        }
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Memory Chat Server — OpenAI-compatible proxy with mem0 augmentation",
    )

    # Chat provider (forwarding)
    parser.add_argument("--chat-api-key", type=str, default=None, help="API key for the chat LLM provider")
    parser.add_argument("--chat-base-url", type=str, default=None, help="Base URL for the chat LLM provider")
    parser.add_argument("--chat-model", type=str, default=None, help="Model name for chat completions")

    # Mem0 LLM (for memory extraction — defaults to chat provider if not set)
    parser.add_argument(
        "--mem0-llm-api-key", type=str, default=None, help="API key for mem0 LLM (default: same as chat)"
    )
    parser.add_argument(
        "--mem0-llm-base-url", type=str, default=None, help="Base URL for mem0 LLM (default: same as chat)"
    )
    parser.add_argument("--mem0-llm-model", type=str, default=None, help="Model for mem0 LLM (default: same as chat)")

    # Embedding
    parser.add_argument("--embedding-api-key", type=str, default=None, help="API key for embedding model")
    parser.add_argument("--embedding-base-url", type=str, default=None, help="Base URL for embedding model")
    parser.add_argument("--embedding-model", type=str, default=None, help="Embedding model name")

    # Identity
    parser.add_argument("--user-id", type=str, default=None, help=f"User ID for mem0 (default: {_DEFAULT_USER_ID})")
    parser.add_argument("--agent-id", type=str, default=None, help=f"Agent ID for mem0 (default: {_DEFAULT_AGENT_ID})")

    # Server
    parser.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    parser.add_argument(
        "--search-limit", type=int, default=_DEFAULT_SEARCH_LIMIT, help="Max memories to recall per request"
    )

    return parser


def main() -> None:
    """CLI entrypoint."""
    _load_dotenv()
    parser = _build_parser()
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

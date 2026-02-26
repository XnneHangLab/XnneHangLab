"""Memory Chat Router — OpenAI-compatible endpoints with mem0 memory augmentation.

This module contains only the FastAPI router and its dependencies (models, memory
logic, state).  It is intentionally decoupled from server startup / CLI so that
the router can be mounted into *any* FastAPI app (e.g. the main XnneHangLab
server).

Standalone usage::

    from memory_bench.server.router import router, state
    app = FastAPI()
    app.include_router(router)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from memory_bench.scripts.bench_logger import logger

if TYPE_CHECKING:
    from openai import OpenAI

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SEARCH_LIMIT = 10
_DEFAULT_USER_ID = "xnne"
_DEFAULT_AGENT_ID = "congyin"

_MEMORY_INJECTION_TEMPLATE = """## Recalled Memories
The following memories were recalled from previous conversations and may be relevant:

{memories}

---
Use these memories naturally in your response when relevant. Do not mention that you "recalled" or "retrieved" them."""


# ---------------------------------------------------------------------------
# Pydantic models (OpenAI-compatible request / response)
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
# Server state — populated by the hosting application at startup
# ---------------------------------------------------------------------------


class ServerState:
    """Mutable singleton holding initialised clients and config."""

    mem0: Any = None
    openai_client: OpenAI | None = None
    chat_model: str = ""
    user_id: str = _DEFAULT_USER_ID
    agent_id: str = _DEFAULT_AGENT_ID
    search_limit: int = _DEFAULT_SEARCH_LIMIT
    api_key: str | None = None  # If set, require Bearer token auth


state = ServerState()


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def _verify_api_key(request: Request) -> None:
    """Validate Bearer token against ``state.api_key``.

    Skipped when ``state.api_key`` is *None* (no auth configured).
    """
    if state.api_key is None:
        return
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.removeprefix("Bearer ").strip()
    if token != state.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------


def _search_memories(query: str) -> list[dict[str, Any]]:
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
        pass
    return []


def _format_memories(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines: list[str] = []
    for i, mem in enumerate(memories, 1):
        text = mem.get("memory", "") or mem.get("data", "") or str(mem)
        score = mem.get("score", "")
        score_str = f" (relevance: {score:.2f})" if isinstance(score, float) else ""
        lines.append(f"{i}. {text}{score_str}")
    return "\n".join(lines)


def _inject_memories(
    messages: list[ChatMessage],
    memories_text: str,
) -> list[ChatMessage]:
    if not memories_text:
        return messages
    injection = _MEMORY_INJECTION_TEMPLATE.format(memories=memories_text)
    result = list(messages)
    for i, msg in enumerate(result):
        if msg.role == "system":
            result[i] = ChatMessage(role="system", content=msg.content + "\n\n" + injection)
            return result
    result.insert(0, ChatMessage(role="system", content=injection))
    return result


# ---------------------------------------------------------------------------
# Async memory write-back
# ---------------------------------------------------------------------------


def _add_memory_sync(user_msg: str, assistant_msg: str) -> None:
    if state.mem0 is None:
        return
    try:
        state.mem0.add(
            messages=[
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ],
            user_id=state.user_id,
            agent_id=state.agent_id,
            metadata={"scene_id": "chill_ai_chat", "character_id": state.agent_id},
        )
    except Exception:
        pass


async def _add_memory_background(user_msg: str, assistant_msg: str) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _add_memory_sync, user_msg, assistant_msg)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter()


@router.post("/v1/chat/completions", dependencies=[Depends(_verify_api_key)])
async def chat_completions(request: ChatCompletionRequest) -> JSONResponse:
    """OpenAI-compatible chat completions with memory augmentation."""
    if state.openai_client is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    if request.stream:
        raise HTTPException(status_code=400, detail="Streaming is not supported yet")

    # 1. Latest user message
    user_messages = [m for m in request.messages if m.role == "user"]
    latest_user_msg = user_messages[-1].content if user_messages else ""

    # 2. Memory search
    memories = _search_memories(latest_user_msg) if latest_user_msg else []
    memories_text = _format_memories(memories)
    if memories:
        logger.info("🔍 Found %d memories for user query", len(memories), group="server")

    # 3. Inject
    augmented = _inject_memories(request.messages, memories_text)

    # 4. Forward to LLM
    model = request.model or state.chat_model
    logger.info("📤 Forwarding to LLM: %s (tokens: max=%d)", model, request.max_tokens or 2000, group="server")
    try:
        completion = state.openai_client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in augmented],
            temperature=request.temperature if request.temperature is not None else 0.7,
            max_completion_tokens=request.max_tokens or 2000,
        )
    except Exception as exc:
        # Log full exception for debugging
        import traceback

        logger.error("❌ LLM provider error: %s", exc, group="server")
        logger.error("%s", traceback.format_exc(), group="server")
        raise HTTPException(status_code=502, detail=f"LLM provider error: {type(exc).__name__}: {exc}") from exc

    assistant_content = completion.choices[0].message.content or ""

    # 5. Async write-back
    if latest_user_msg and assistant_content:
        logger.info("💾 Queued memory write-back (async)", group="server")
        asyncio.create_task(_add_memory_background(latest_user_msg, assistant_content))

    # 6. Response
    resp = ChatCompletionResponse(
        model=model,
        choices=[ChatCompletionChoice(message=ChatMessage(role="assistant", content=assistant_content))],
        usage=UsageInfo(
            prompt_tokens=getattr(completion.usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(completion.usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(completion.usage, "total_tokens", 0) or 0,
        ),
    )
    return JSONResponse(content=json.loads(resp.model_dump_json()))


@router.get("/v1/models")
async def list_models() -> JSONResponse:
    """Minimal /v1/models endpoint for compatibility."""
    return JSONResponse(
        content={
            "object": "list",
            "data": [{"id": state.chat_model, "object": "model", "owned_by": "memory-chat-server"}],
        }
    )


@router.get("/health")
async def health() -> JSONResponse:
    """Health check."""
    return JSONResponse(
        content={
            "status": "ok",
            "mem0_ready": state.mem0 is not None,
            "llm_ready": state.openai_client is not None,
            "model": state.chat_model,
        }
    )

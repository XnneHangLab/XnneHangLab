# pyright: reportUnknownVariableType=none, reportUnknownMemberType=none, reportUnknownArgumentType=none, reportMissingTypeArgument=none
"""Chat Route — Autonomous agent endpoint with tool calling and memory integration.

This module provides the ``/chat`` endpoint for lightweight clients (e.g. AIChat).
The server manages sessions, context, tool execution, and system prompt generation.

Key features:
- System prompt 拼接 from modular files (persona, emotion, tools, diary)
- Tool calling via ``ToolManager`` (BuiltinTools, no MCP dependency)
- Memory integration via ``memory_bench`` (search + write-back, direct import)
- Date-based conversation persistence via ``ConversationStore``

Architecture note:
  This route lives in ``src/lab`` (the "body") and imports memory functions
  from ``memory_bench`` (the "brain"). See #262 for the design rationale.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request  # type: ignore[reportMissingImports]
from fastapi.responses import JSONResponse  # type: ignore[reportMissingImports]
from loguru import logger
from pydantic import BaseModel  # type: ignore[reportMissingImports]

from lab.conversation.store import ConversationStore

if TYPE_CHECKING:
    from lab.agent.core import AgentCore


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Chat request model."""

    session_id: str | None = None
    message: str
    model: str | None = None
    model_config = {"extra": "allow"}


class ChatResponse(BaseModel):
    """Chat response model."""

    session_id: str
    content: str
    model: str
    created: int


# ---------------------------------------------------------------------------
# Server state
# ---------------------------------------------------------------------------


class ChatState:
    """Mutable singleton holding chat endpoint config.

    Populated at application startup (in ``server.py`` lifespan).
    Requires agent_core to be initialized via AgentFactory.create_core_with_profile().
    """

    chat_model: str = ""
    conversations_dir: str = "conversations"
    workspace_root: str = ""
    agent_core: AgentCore | None = None


chat_state = ChatState()


# ---------------------------------------------------------------------------
# Memory helpers (delegated to memory_bench)
# ---------------------------------------------------------------------------

_MEMORY_INJECTION_TEMPLATE = """## Recalled Memories
The following memories were recalled from previous conversations and may be relevant:

{memories}

---
Use these memories naturally in your response when relevant. Do not mention that you "recalled" or "retrieved" them."""


def _search_and_format_memories(query: str) -> str:
    """Search memories and format for injection into system prompt.

    Graceful degradation: returns empty string if memory_bench is unavailable.
    """
    if not query:
        return ""
    try:
        from memory_bench.server.router import format_memories, search_memories  # type: ignore[reportMissingImports]

        memories = search_memories(query)
        if not memories:
            return ""
        formatted = format_memories(memories)
        logger.bind(group="chat").info(f"🔍 Found {len(memories)} memories for query")
        return _MEMORY_INJECTION_TEMPLATE.format(memories=formatted)
    except ImportError:
        logger.bind(group="chat").warning("⚠️  memory_bench not available, skipping memory search")
        return ""
    except Exception as exc:
        logger.bind(group="chat").warning(f"⚠️  Memory search failed: {exc}")
        return ""


async def _writeback_memory(user_msg: str, assistant_msg: str) -> None:
    """Queue async memory write-back (mem0 + graph pipeline).

    Graceful degradation: does nothing if memory_bench is unavailable.
    """
    try:
        from memory_bench.server.router import memory_and_graph_background  # type: ignore[reportMissingImports]

        await memory_and_graph_background(user_msg, assistant_msg)
    except ImportError:
        pass
    except Exception as exc:
        logger.bind(group="chat").warning(f"⚠️  Memory write-back failed: {exc}")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

chat_router = APIRouter()


@chat_router.post("/chat", response_model=None)
async def chat_endpoint(request: ChatRequest, http_request: Request) -> JSONResponse:
    """处理 autonomous chat 请求。

    Args:
        request: 聊天请求体，包含会话 ID、消息文本和可选模型名。
        http_request: FastAPI 原始 HTTP 请求对象。

    Returns:
        标准 JSONResponse，包含 session_id、content、model 和 created 字段。
    """
    if chat_state.agent_core is None:
        raise HTTPException(status_code=503, detail="Chat endpoint not initialized — agent_core is None")

    log = logger.bind(group="chat")

    # 1. Session ID
    session_id = request.session_id or f"sess_{uuid.uuid4().hex[:12]}"
    log.info(f"💬 Chat request: session={session_id}, message_len={len(request.message)}")

    from datetime import datetime, timezone

    date_id = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # noqa: UP017
    model = request.model or chat_state.chat_model
    assistant_content = ""

    try:
        # 检索 memory context，传给 AgentCore
        loop = asyncio.get_running_loop()
        memories_text = await loop.run_in_executor(None, _search_and_format_memories, request.message)
        async for token in chat_state.agent_core.run_turn(
            user_text=request.message,
            memory_context=memories_text or None,
        ):
            assistant_content += token
    except Exception as exc:
        import traceback

        log.error(f"❌ LLM error: {exc}")
        log.error(traceback.format_exc())
        raise HTTPException(
            status_code=502,
            detail=f"LLM error: {type(exc).__name__}: {exc}",
        ) from exc

    log.info(f"📥 LLM response: {len(assistant_content)} chars")

    # 7. Memory write-back (async, non-blocking)
    if request.message and assistant_content:
        log.info("💾 Queued memory write-back (async)")
        asyncio.create_task(_writeback_memory(request.message, assistant_content))

    # 8. Response
    created = int(time.time())
    response = ChatResponse(
        session_id=session_id,
        content=assistant_content,
        model=model,
        created=created,
    )

    log.info(f"✅ Chat response sent (session={session_id}, date={date_id})")
    return JSONResponse(content=json.loads(response.model_dump_json()))


@chat_router.get("/sessions", response_model=None)
async def list_sessions() -> JSONResponse:
    """List available conversation dates."""
    conv_store = ConversationStore(base_dir=chat_state.conversations_dir)
    dates = conv_store.list_conversations()
    return JSONResponse(content={"sessions": dates, "count": len(dates)})


@chat_router.get("/chat/health", response_model=None)
async def chat_health() -> JSONResponse:
    """Health check for chat endpoint."""
    core = chat_state.agent_core
    return JSONResponse(
        content={
            "status": "ok",
            "agent_core_ready": core is not None,
            "model": chat_state.chat_model,
            "conversations_dir": chat_state.conversations_dir,
        }
    )

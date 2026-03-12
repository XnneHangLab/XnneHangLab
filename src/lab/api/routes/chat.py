# pyright: reportUnknownVariableType=none, reportUnknownMemberType=none, reportUnknownArgumentType=none, reportMissingTypeArgument=none
"""Autonomous chat endpoint backed by AgentCore."""

from __future__ import annotations

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


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    model: str | None = None
    model_config = {"extra": "allow"}


class ChatResponse(BaseModel):
    session_id: str
    content: str
    model: str
    created: int


class ChatState:
    """Mutable singleton populated during server startup."""

    chat_model: str = ""
    conversations_dir: str = "conversations"
    workspace_root: str = ""
    agent_core: AgentCore | None = None


chat_state = ChatState()
chat_router = APIRouter()


@chat_router.post("/chat", response_model=None)
async def chat_endpoint(request: ChatRequest, http_request: Request) -> JSONResponse:
    del http_request

    if chat_state.agent_core is None:
        raise HTTPException(status_code=503, detail="Chat endpoint not initialized: agent_core is None")

    log = logger.bind(group="chat")
    session_id = request.session_id or f"sess_{uuid.uuid4().hex[:12]}"
    log.info("Chat request: session={}, message_len={}", session_id, len(request.message))

    from datetime import datetime, timezone

    date_id = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # noqa: UP017
    model = request.model or chat_state.chat_model
    assistant_content = ""

    try:
        async for token in chat_state.agent_core.run_turn(user_text=request.message):
            assistant_content += token
    except Exception as exc:
        import traceback

        log.error("LLM error: {}", exc)
        log.error(traceback.format_exc())
        raise HTTPException(
            status_code=502,
            detail=f"LLM error: {type(exc).__name__}: {exc}",
        ) from exc

    log.info("LLM response: {} chars", len(assistant_content))

    response = ChatResponse(
        session_id=session_id,
        content=assistant_content,
        model=model,
        created=int(time.time()),
    )
    log.info("Chat response sent (session={}, date={})", session_id, date_id)
    return JSONResponse(content=json.loads(response.model_dump_json()))


@chat_router.get("/sessions", response_model=None)
async def list_sessions() -> JSONResponse:
    conv_store = ConversationStore(base_dir=chat_state.conversations_dir)
    dates = conv_store.list_conversations()
    return JSONResponse(content={"sessions": dates, "count": len(dates)})


@chat_router.get("/chat/health", response_model=None)
async def chat_health() -> JSONResponse:
    core = chat_state.agent_core
    return JSONResponse(
        content={
            "status": "ok",
            "agent_core_ready": core is not None,
            "model": chat_state.chat_model,
            "conversations_dir": chat_state.conversations_dir,
        }
    )

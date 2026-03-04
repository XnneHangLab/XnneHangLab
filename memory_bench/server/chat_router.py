"""Chat Router — Autonomous agent endpoint with session management.

This module provides the `/memory/chat` endpoint for lightweight clients (e.g., AIChat).
The server manages sessions, context, and system prompt generation.

Key features:
- System prompt拼接 from modular files (persona, emotion, tools, diary)
- Date-based conversation persistence (conversations/YYYY-MM-DD.json)
- Session management (in-memory, with file recovery)

Usage::

    from memory_bench.server.chat_router import router, chat_state

    app = FastAPI()
    app.include_router(router, prefix="/memory")
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request  # type: ignore[reportMissingImports]
from fastapi.responses import JSONResponse  # type: ignore[reportMissingImports]
from pydantic import BaseModel, Field  # type: ignore[reportMissingImports]

from memory_bench.scripts.bench_logger import logger

# Avoid importing typing module due to conflict with local typing/ directory
# Use object instead of Any, and skip cast() - both work fine with PEP 563

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CHAT_MODEL = "gpt-4o-mini"
_DEFAULT_SESSION_TTL = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """Single chat message."""

    role: str
    content: str


class ChatRequest(BaseModel):
    """Chat request model."""

    session_id: str | None = None  # If None, create new session
    message: str
    model: str | None = None
    model_config = {"extra": "allow"}


class ChatResponse(BaseModel):
    """Chat response model."""

    session_id: str
    content: str  # Changed from 'message' to 'content' for AIChat client compatibility
    model: str
    created: int


# ---------------------------------------------------------------------------
# Server state
# ---------------------------------------------------------------------------


class ChatServerState:
    """Mutable singleton holding chat server config."""

    openai_client: object = None  # type: ignore[reportUnknownVariableType]  # OpenAI client
    chat_model: str = _DEFAULT_CHAT_MODEL
    session_ttl: int = _DEFAULT_SESSION_TTL
    prompts_dir: str = ""  # Path to prompts/ directory
    conversations_dir: str = "conversations"  # Path to conversations/ directory


chat_state = ChatServerState()


# ---------------------------------------------------------------------------
# System Prompt Builder
# ---------------------------------------------------------------------------


def _load_prompt_file(file_path: Path) -> str | None:
    """Load a prompt file if it exists and is not empty/placeholder.

    Args:
        file_path: Path to the prompt file

    Returns:
        File content if valid, None if empty or placeholder
    """
    if not file_path.exists():
        return None

    try:
        content = file_path.read_text(encoding="utf-8")

        # Skip if empty or just placeholder comments
        stripped = content.strip()
        if not stripped:
            return None
        if stripped.startswith("[") and ("待补充" in stripped or "TODO" in stripped):
            return None

        return content
    except Exception:
        return None


def _build_system_prompt() -> str:
    """Build system prompt by concatenating modular files.

    Order:
    1. [persona] base_persona.txt
    2. [emotion] emotion_system.txt
    3. [tool] tool_definitions.txt (optional, skip if empty)
    4. [diary] recent_summary.txt (optional, skip if empty)

    Returns:
        Concatenated system prompt
    """
    log = logger.bind(group="chat_router")
    parts: list[str] = []

    if not chat_state.prompts_dir:
        log.warning("⚠️  prompts_dir not configured, using minimal system prompt")
        return "You are a helpful assistant."

    prompts_path = Path(chat_state.prompts_dir)

    # 1. Base persona
    persona_file = prompts_path / "emotion" / "base_persona.txt"
    persona_content = _load_prompt_file(persona_file)
    if persona_content:
        parts.append(persona_content)
        log.info("✅ Loaded persona from %s", persona_file)
    else:
        log.warning("⚠️  Persona file not found or empty: %s", persona_file)

    # 2. Emotion system
    emotion_file = prompts_path / "emotion" / "emotion_system.txt"
    emotion_content = _load_prompt_file(emotion_file)
    if emotion_content:
        parts.append(emotion_content)
        log.info("✅ Loaded emotion system from %s", emotion_file)
    else:
        log.warning("⚠️  Emotion file not found or empty: %s", emotion_file)

    # 3. Tool definitions (optional)
    tool_file = prompts_path / "tools" / "tool_definitions.txt"
    tool_content = _load_prompt_file(tool_file)
    if tool_content:
        parts.append(tool_content)
        log.info("✅ Loaded tool definitions from %s", tool_file)

    # 4. Diary summary (optional)
    diary_file = prompts_path / "diary" / "recent_summary.txt"
    diary_content = _load_prompt_file(diary_file)
    if diary_content:
        parts.append(diary_content)
        log.info("✅ Loaded diary summary from %s", diary_file)

    if not parts:
        log.error("❌ No valid prompt files found, using fallback")
        return "You are a helpful assistant."

    # Concatenate with double newlines
    system_prompt = "\n\n".join(parts)
    log.info("✅ Built system prompt (%d parts, %d chars)", len(parts), len(system_prompt))

    return system_prompt


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter()  # type: ignore[reportUnknownVariableType]


@router.post("/chat")  # type: ignore[reportUnknownMemberType,reportUntypedFunctionDecorator]
async def chat_endpoint(request: ChatRequest, http_request: Request) -> JSONResponse:  # type: ignore[reportUnknownParameterType]
    """Autonomous chat endpoint with session management.

    This endpoint:
    1. Creates or retrieves a session
    2. Loads conversation history from date-based JSON file
    3. Builds system prompt from modular files
    4. Calls LLM with full context
    5. Saves response to conversation file
    6. Returns response

    Args:
        request: Chat request (session_id, message, model)
        http_request: HTTP request (for metadata)

    Returns:
        JSON response (session_id, message, model, created)
    """
    if chat_state.openai_client is None:  # type: ignore[reportUnknownMemberType]
        raise HTTPException(status_code=503, detail="Chat server not initialized")

    log = logger.bind(group="chat_router")

    # 1. Session ID (create new if not provided)
    session_id = request.session_id or f"sess_{uuid.uuid4().hex[:12]}"
    log.info("💬 Chat request: session=%s, message_len=%d", session_id, len(request.message))

    # 2. Get today's date ID for conversation file
    from datetime import datetime, timezone

    date_id = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # noqa: UP017

    # 3. Import conversation store and load history
    from memory_bench.server.conversation_store import ConversationStore

    conv_store = ConversationStore(base_dir=chat_state.conversations_dir)

    # Load existing conversation messages
    conv_messages = conv_store.read_conversation(date_id)

    # Convert to OpenAI format (only role + content)
    messages: list[dict] = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in conv_messages
        if msg.get("role") in ("user", "assistant")
    ]

    log.info("📚 Loaded %d conversation messages from %s", len(messages), date_id)

    # 4. Build system prompt
    system_prompt = _build_system_prompt()

    # 5. Prepare full message list (system + conversation + new user message)
    full_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    full_messages.extend(messages)
    full_messages.append({"role": "user", "content": request.message})

    # 6. Call LLM
    model = request.model or chat_state.chat_model
    log.info("📤 Calling LLM: %s (messages: %d)", model, len(full_messages))

    try:
        completion = chat_state.openai_client.chat.completions.create(  # type: ignore[reportUnknownMemberType]
            model=model,
            messages=full_messages,  # type: ignore[reportArgumentType]
            temperature=0.7,
            max_completion_tokens=2000,
        )
    except Exception as exc:
        import traceback

        log.error("❌ LLM provider error: %s", exc)
        log.error("%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail=f"LLM provider error: {type(exc).__name__}: {exc}") from exc

    assistant_content = completion.choices[0].message.content or ""  # type: ignore[reportUnknownMemberType,reportUnknownVariableType]
    log.info("📥 LLM response: %d chars", len(assistant_content))

    # 7. Save to conversation store (user + assistant turns)
    conv_store.append_turn(date_id, role="user", content=request.message)
    conv_store.append_turn(date_id, role="assistant", content=assistant_content)

    # 8. Build response
    created = int(time.time())
    response = ChatResponse(
        session_id=session_id,
        content=assistant_content,  # Changed from 'message' to 'content'
        model=model,
        created=created,
    )

    log.info("✅ Chat response sent (session=%s, date=%s)", session_id, date_id)

    return JSONResponse(content=json.loads(response.model_dump_json()))  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]


@router.get("/sessions")  # type: ignore[reportUnknownMemberType,reportUntypedFunctionDecorator]
async def list_sessions() -> JSONResponse:  # type: ignore[reportUnknownParameterType,reportUnknownVariableType]
    """List available conversation dates.

    Returns:
        JSON response with list of date IDs
    """
    from memory_bench.server.conversation_store import ConversationStore

    conv_store = ConversationStore(base_dir=chat_state.conversations_dir)
    dates = conv_store.list_conversations()

    return JSONResponse(content={"sessions": dates, "count": len(dates)})  # type: ignore[reportUnknownArgumentType]


@router.get("/health")  # type: ignore[reportUnknownMemberType,reportUntypedFunctionDecorator]
async def health() -> JSONResponse:  # type: ignore[reportUnknownParameterType,reportUnknownVariableType]
    """Health check for chat endpoint.

    Returns:
        JSON response with status
    """
    return JSONResponse(  # type: ignore[reportUnknownArgumentType]
        content={
            "status": "ok",
            "llm_ready": chat_state.openai_client is not None,  # type: ignore[reportUnknownMemberType]
            "model": chat_state.chat_model,
            "prompts_dir": chat_state.prompts_dir or None,
            "conversations_dir": chat_state.conversations_dir,
        }
    )

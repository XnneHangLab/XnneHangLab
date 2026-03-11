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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request  # type: ignore[reportMissingImports]
from fastapi.responses import JSONResponse  # type: ignore[reportMissingImports]
from loguru import logger
from pydantic import BaseModel  # type: ignore[reportMissingImports]

from lab.conversation.store import ConversationStore

if TYPE_CHECKING:
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.profile.context_injector import ContextInjector
    from lab.profile.schema import Profile
    from lab.tools import AgentContext, ToolManager


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_TOOL_STEPS = 6


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

    Prompt paths follow the 5-layer system prompt architecture
    (see docs/architecture/system-prompt-layers.md):
    - persona_file: Layer 1 (character identity)
    - format_file: Layer 2 (output format constraints)
    - skill_files: Layer 3 (behavioral strategies)
    - Layer 4 (tools) is auto-generated from ToolManager
    - Layer 5 (context) is injected per-request at runtime
    """

    chat_llm: AsyncLLM | None = None
    tool_manager: ToolManager | None = None
    agent_context: AgentContext | None = None
    chat_model: str = ""
    conversations_dir: str = "conversations"

    # --- Prompt layers (configurable per profile) ---
    persona_file: str = ""  # Layer 1: e.g. "prompts/characters/satone.md"
    format_file: str = ""  # Layer 2: e.g. "prompts/formats/emotion_pipe.md"
    skill_files: list[str] | None = None  # Layer 3: e.g. ["prompts/skills/diary_writing.md", ...]
    workspace_root: str = ""  # For resolving relative prompt paths
    profile: Profile | None = None
    context_injector: ContextInjector | None = None
    skill_descriptors: list[Any] | None = None


chat_state = ChatState()


# ---------------------------------------------------------------------------
# System Prompt Builder
# ---------------------------------------------------------------------------


def _load_prompt_file(file_path: Path) -> str | None:
    """Load a prompt file if it exists and is not empty/placeholder."""
    if not file_path.exists():
        return None
    try:
        content = file_path.read_text(encoding="utf-8")
        stripped = content.strip()
        if not stripped:
            return None
        if stripped.startswith("[") and ("待补充" in stripped or "TODO" in stripped):
            return None
        return content
    except Exception:
        return None


def _build_system_prompt() -> str:
    """Build system prompt following the 5-layer architecture.

    See docs/architecture/system-prompt-layers.md for design rationale.

    Layers:
    1. Persona — character identity (from persona_file)
    2. Format — output format constraints (from format_file)
    3. Skills — behavioral strategies (from skill_files)
    4. Tools — auto-generated from ToolManager
    5. Context — injected per-request (memories, diary summaries) — NOT here, done in chat_endpoint
    """
    if chat_state.profile is not None and chat_state.workspace_root:
        from lab.profile.system_prompt_builder import SystemPromptBuilder

        return SystemPromptBuilder(Path(chat_state.workspace_root)).build(
            persona_path=chat_state.profile.prompt.persona,
            format_path=chat_state.profile.prompt.format,
            skills=chat_state.skill_descriptors or [],
            tool_manager=chat_state.tool_manager,
        )

    log = logger.bind(group="chat")
    parts: list[str] = []

    ws_root = Path(chat_state.workspace_root) if chat_state.workspace_root else None

    def _resolve_and_load(rel_path: str, layer_name: str) -> str | None:
        """Resolve relative path against workspace_root and load."""
        if not rel_path:
            return None
        if ws_root is not None:
            full_path = ws_root / rel_path
        else:
            full_path = Path(rel_path)
        content = _load_prompt_file(full_path)
        if content:
            log.info(f"✅ [{layer_name}] Loaded: {rel_path}")
        else:
            log.warning(f"⚠️  [{layer_name}] Not found or empty: {full_path}")
        return content

    # Layer 1: Persona
    persona = _resolve_and_load(chat_state.persona_file, "persona")
    if persona:
        parts.append(persona)

    # Layer 2: Format
    fmt = _resolve_and_load(chat_state.format_file, "format")
    if fmt:
        parts.append(fmt)

    # Layer 3: Skills
    if chat_state.skill_files:
        for skill_path in chat_state.skill_files:
            skill = _resolve_and_load(skill_path, "skill")
            if skill:
                parts.append(skill)

    # Layer 4: Tools (auto-generated)
    if chat_state.tool_manager is not None:
        tool_prompt = chat_state.tool_manager.build_system_prompt(
            preamble="你可以使用以下工具来帮助完成任务：",
            include_mcp=False,
        )
        if tool_prompt.strip():
            parts.append(tool_prompt)
            log.info("✅ [tools] Generated from ToolManager")

    # Layer 5: Context is NOT added here — it's per-request, added in chat_endpoint

    if not parts:
        log.error("❌ No valid prompt layers loaded, using fallback")
        return "You are a helpful assistant."

    system_prompt = "\n\n---\n\n".join(parts)
    log.info(f"✅ Built system prompt ({len(parts)} layers, {len(system_prompt)} chars)")
    return system_prompt


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
# Tool Loop (lightweight, ToolManager-only)
# ---------------------------------------------------------------------------


async def _run_tool_loop(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    max_steps: int = _MAX_TOOL_STEPS,
) -> str:
    """Run a simple tool-calling loop using ToolManager + AsyncLLM.

    1. Call LLM with tools
    2. If tool_calls → ToolManager.call_tool() → append tool messages → re-call LLM
    3. No tool_calls → return final content

    No MCP, no ConversationState, no ToolRegistry — just ToolManager.
    """
    log = logger.bind(group="chat")

    assert chat_state.chat_llm is not None
    assert chat_state.tool_manager is not None
    assert chat_state.agent_context is not None

    from lab.mcp import OpenAIMessage

    # Convert dict messages to OpenAIMessage for AsyncLLM
    oai_messages = [OpenAIMessage.model_validate(m) for m in messages]

    for step in range(max_steps):
        # Non-streaming tool completion
        completion = await chat_state.chat_llm.tool_completion(
            messages=oai_messages,
            tools=tools,
            tool_choice="auto",
            system=None,  # system is already in messages
        )

        assistant_message = completion.choices[0].message
        tool_calls = getattr(assistant_message, "tool_calls", None)

        if not tool_calls:
            # No tool calls — we're done
            return assistant_message.content or ""

        log.info(f"🔧 Step {step}: LLM returned {len(tool_calls)} tool_call(s)")

        # Append assistant message (with tool_calls) to conversation
        assistant_dict: dict[str, Any] = {
            "role": "assistant",
            "content": assistant_message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        }
        oai_messages.append(OpenAIMessage.model_validate(assistant_dict))

        # Execute each tool call via ToolManager
        for tc in tool_calls:
            tool_name = tc.function.name
            args_json = tc.function.arguments or "{}"

            log.info(f"🛠️  Executing: {tool_name}({args_json[:200]})")

            result = await chat_state.tool_manager.call_tool(
                tool_name,
                args_json,
                chat_state.agent_context,
            )

            tool_content = result.text if result.ok else f"Error: {result.error}"

            oai_messages.append(
                OpenAIMessage.model_validate(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_content,
                    }
                )
            )

    # Exhausted max_steps — do one final call without tools
    log.warning(f"⚠️  Tool loop exhausted {max_steps} steps, doing final call without tools")
    final_content = ""
    async for token in chat_state.chat_llm.chat_completion(oai_messages, system=None, stream_=False):
        final_content += token
    return final_content


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

chat_router = APIRouter()


@chat_router.post("/chat", response_model=None)
async def chat_endpoint(request: ChatRequest, http_request: Request) -> JSONResponse:
    """Autonomous chat endpoint with tool calling and memory integration.

    Flow:
    1. Create/retrieve session
    2. Load conversation history
    3. Search memories → inject into system prompt
    4. Build system prompt (persona + format + skills + tools + memories)
    5. Run tool loop (ToolManager + AsyncLLM)
    6. Write-back memories (async)
    7. Save to conversation store
    """
    if chat_state.chat_llm is None:
        raise HTTPException(status_code=503, detail="Chat endpoint not initialized")

    log = logger.bind(group="chat")

    # 1. Session ID
    session_id = request.session_id or f"sess_{uuid.uuid4().hex[:12]}"
    log.info(f"💬 Chat request: session={session_id}, message_len={len(request.message)}")

    # 2. Load conversation history
    from datetime import datetime, timezone

    date_id = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # noqa: UP017
    conv_store = ConversationStore(base_dir=chat_state.conversations_dir)
    conv_messages = conv_store.read_conversation(date_id)

    history: list[dict[str, str]] = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in conv_messages
        if msg.get("role") in ("user", "assistant")
    ]
    log.info(f"📚 Loaded {len(history)} conversation messages from {date_id}")

    # 3. Search memories
    loop = asyncio.get_running_loop()
    memories_text = await loop.run_in_executor(None, _search_and_format_memories, request.message)

    # 4. Build system prompt
    system_prompt = _build_system_prompt()

    # 5. Build full message list
    full_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    full_messages.extend(history)

    # Inject memory context into user message
    user_content = request.message
    if memories_text:
        if chat_state.context_injector is not None:
            injected = chat_state.context_injector.build_context_prompt(memory_context=memories_text)
            if injected:
                user_content = injected + "\n\n" + user_content
        else:
            user_content = memories_text + "\n\n" + user_content
    full_messages.append({"role": "user", "content": user_content})

    # 6. Run tool loop or plain chat
    model = request.model or chat_state.chat_model
    log.info(f"📤 Calling LLM: {model} (messages: {len(full_messages)})")

    try:
        if chat_state.tool_manager is not None:
            tools = chat_state.tool_manager.list_tools_schema()
            assistant_content = await _run_tool_loop(
                messages=full_messages,
                tools=tools,
                model=model,
            )
        else:
            # No tools — plain chat
            from lab.mcp import OpenAIMessage

            oai_msgs = [OpenAIMessage.model_validate(m) for m in full_messages]
            assistant_content = ""
            async for token in chat_state.chat_llm.chat_completion(oai_msgs, system=None, stream_=False):
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

    # 8. Save to conversation store
    conv_store.append_turn(date_id, role="user", content=request.message)
    conv_store.append_turn(date_id, role="assistant", content=assistant_content)

    # 9. Response
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
    tools_count = 0
    if chat_state.tool_manager is not None:
        tools_count = len(chat_state.tool_manager.list_tools_schema())

    return JSONResponse(
        content={
            "status": "ok",
            "llm_ready": chat_state.chat_llm is not None,
            "model": chat_state.chat_model,
            "tools_count": tools_count,
            "profile": chat_state.profile.profile.name if chat_state.profile else None,
            "persona_file": chat_state.persona_file or None,
            "format_file": chat_state.format_file or None,
            "skill_files": chat_state.skill_files,
            "conversations_dir": chat_state.conversations_dir,
        }
    )

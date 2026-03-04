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
# Tool Definitions (JSON Schema for Function Calling)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "READ",
            "description": "读取文件内容或列出目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（相对路径或绝对路径）"},
                    "purpose": {
                        "type": "string",
                        "enum": ["memory", "diary", "saved", "prompt", "conversation"],
                        "description": "预设位置快捷方式（当 path 未提供时使用）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "WRITE",
            "description": "创建或覆盖文件（仅限 memory_bench/ 内部）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件相对路径（必须在 memory_bench/ 内部）"},
                    "content": {"type": "string", "description": "文件内容"},
                    "purpose": {
                        "type": "string",
                        "enum": ["diary", "saved"],
                        "description": "预设位置快捷方式（当 path 未提供时使用）",
                    },
                    "append": {"type": "boolean", "description": "是否追加模式", "default": False},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "EDIT",
            "description": "精确替换文件中的文本（仅限 memory_bench/ 内部）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件相对路径（必须在 memory_bench/ 内部）"},
                    "old_text": {"type": "string", "description": "要替换的原文（必须精确匹配）"},
                    "new_text": {"type": "string", "description": "新内容"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "SEARCH",
            "description": "在指定范围内搜索关键词",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "scope": {
                        "type": "string",
                        "enum": ["workspace", "memory_bench", "diary", "prompts", "saved"],
                        "description": "搜索范围",
                    },
                    "file_pattern": {"type": "string", "description": "文件通配符（如 *.py, *.md, *）", "default": "*"},
                    "context_lines": {"type": "integer", "description": "上下文行数", "default": 2},
                },
                "required": ["query"],
            },
        },
    },
]


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
    messages: list[dict[str, str]] = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in conv_messages
        if msg.get("role") in ("user", "assistant")
    ]

    log.info("📚 Loaded %d conversation messages from %s", len(messages), date_id)

    # 4. Build system prompt
    system_prompt = _build_system_prompt()

    # 5. Prepare full message list (system + conversation + new user message)
    full_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    full_messages.extend(messages)
    full_messages.append({"role": "user", "content": request.message})

    # 6. Call LLM with tools (function calling)
    model = request.model or chat_state.chat_model
    log.info(
        "📤 Calling LLM: %s (messages: %d, tools: %d)",
        model,
        len(full_messages),
        len(TOOL_DEFINITIONS),
    )

    try:
        completion = chat_state.openai_client.chat.completions.create(  # type: ignore[reportUnknownMemberType]
            model=model,
            messages=full_messages,  # type: ignore[reportArgumentType]
            tools=TOOL_DEFINITIONS,  # type: ignore[reportArgumentType]
            tool_choice="auto",
            temperature=0.7,
            max_completion_tokens=2000,
        )
    except Exception as exc:
        import traceback

        log.error("❌ LLM provider error: %s", exc)
        log.error("%s", traceback.format_exc())
        raise HTTPException(
            status_code=502,
            detail=f"LLM provider error: {type(exc).__name__}: {exc}",
        ) from exc

    # 7. Tool-loop: execute tools if LLM returned tool_calls
    assistant_message = completion.choices[0].message  # type: ignore[reportUnknownMemberType]

    # Check if LLM wants to call tools
    while hasattr(assistant_message, "tool_calls") and assistant_message.tool_calls:  # type: ignore[reportUnknownMemberType]
        log.info(
            "🔧 LLM returned %d tool_call(s), executing...",
            len(assistant_message.tool_calls),  # type: ignore[reportUnknownMemberType]
        )

        # Add assistant's tool_call message to conversation
        full_messages.append(
            {
                "role": "assistant",
                "content": assistant_message.content or "",  # type: ignore[reportUnknownMemberType]
                "tool_calls": [  # type: ignore[reportUnknownMemberType]
                    {
                        "id": tc.id,  # type: ignore[reportUnknownMemberType]
                        "type": "function",
                        "function": {
                            "name": tc.function.name,  # type: ignore[reportUnknownMemberType]
                            "arguments": tc.function.arguments,  # type: ignore[reportUnknownMemberType]
                        },
                    }
                    for tc in assistant_message.tool_calls  # type: ignore[reportUnknownMemberType]
                ],
            }
        )

        # Execute each tool call
        for tc in assistant_message.tool_calls:  # type: ignore[reportUnknownMemberType]
            tool_name = tc.function.name  # type: ignore[reportUnknownMemberType]
            tool_args = json.loads(tc.function.arguments)  # type: ignore[reportUnknownMemberType]
            log.info("🛠️  Executing tool: %s(%s)", tool_name, tool_args)

            # Execute tool and get result
            tool_result = await _execute_tool(tool_name, tool_args, log)

            # Add tool result to messages
            full_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,  # type: ignore[reportUnknownMemberType]
                    "content": tool_result,
                }
            )

        # Call LLM again with tool results
        log.info(
            "📤 Calling LLM again with tool results (messages: %d)",
            len(full_messages),
        )
        completion = chat_state.openai_client.chat.completions.create(  # type: ignore[reportUnknownMemberType]
            model=model,
            messages=full_messages,  # type: ignore[reportArgumentType]
            tools=TOOL_DEFINITIONS,  # type: ignore[reportArgumentType]
            tool_choice="auto",
            temperature=0.7,
            max_completion_tokens=2000,
        )
        assistant_message = completion.choices[0].message  # type: ignore[reportUnknownMemberType]

    # 8. Extract final response (no more tool_calls)
    assistant_content: str = assistant_message.content or ""  # type: ignore[reportUnknownMemberType,reportUnknownVariableType]
    log.info("📥 LLM final response: %d chars", len(assistant_content))

    # 9. Save to conversation store (user + assistant turns)
    conv_store.append_turn(date_id, role="user", content=request.message)
    conv_store.append_turn(date_id, role="assistant", content=assistant_content)  # type: ignore[reportUnknownArgumentType]

    # 10. Build response
    created = int(time.time())
    response = ChatResponse(
        session_id=session_id,
        content=assistant_content,  # type: ignore[reportUnknownArgumentType]
        model=model,
        created=created,
    )

    log.info("✅ Chat response sent (session=%s, date=%s)", session_id, date_id)

    return JSONResponse(content=json.loads(response.model_dump_json()))  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------


async def _execute_tool(tool_name: str, tool_args: dict, log: object) -> str:  # type: ignore[reportUnknownParameterType,reportUnknownVariableType]
    """Execute a tool call and return the result.

    Args:
        tool_name: Tool name (READ / WRITE / EDIT / SEARCH)
        tool_args: Tool arguments (parsed from LLM response)
        log: Logger instance

    Returns:
        Tool result as string (to be sent back to LLM)
    """
    from memory_bench.server.tools.file_tools import (  # type: ignore[reportUnknownVariableType]
        FileTools,
        SecurityError,
    )
    from memory_bench.server.tools.search_tools import (  # type: ignore[reportUnknownVariableType]
        SearchTools,
    )

    # Initialize tools (workspace and memory_bench paths)
    workspace = Path(__file__).parent.parent.parent  # /wangwang/workspace/XnneHangLab
    memory_bench = workspace / "XnneHangLab" / "memory_bench"

    file_tools = FileTools(workspace=workspace, memory_bench=memory_bench)
    search_tools = SearchTools(workspace=workspace, memory_bench=memory_bench)

    try:
        if tool_name == "READ":
            path = tool_args.get("path")
            purpose = tool_args.get("purpose")
            result = file_tools.read(path=path, purpose=purpose)
            if result.success:
                log.info("✅ READ success: %s", result.path)
                return f"File content:\n{result.content}" if result.content else f"Directory listing:\n{result.content}"
            else:
                log.error("❌ READ failed: %s", result.error)
                return f"Error: {result.error}"

        elif tool_name == "WRITE":
            content = tool_args.get("content", "")
            path = tool_args.get("path")
            purpose = tool_args.get("purpose")
            append = tool_args.get("append", False)
            result = file_tools.write(content=content, path=path, purpose=purpose, append=append)
            if result.success:
                log.info("✅ WRITE success: %s", result.path)
                return f"Successfully wrote to {result.path}"
            else:
                log.error("❌ WRITE failed: %s", result.error)
                return f"Error: {result.error}"

        elif tool_name == "EDIT":
            path = tool_args.get("path", "")
            old_text = tool_args.get("old_text", "")
            new_text = tool_args.get("new_text", "")
            result = file_tools.edit(path=path, old_text=old_text, new_text=new_text)
            if result.success:
                log.info("✅ EDIT success: %s", result.path)
                return f"Successfully edited {result.path}"
            else:
                log.error("❌ EDIT failed: %s", result.error)
                return f"Error: {result.error}"

        elif tool_name == "SEARCH":
            query = tool_args.get("query", "")
            scope = tool_args.get("scope", "workspace")
            file_pattern = tool_args.get("file_pattern", "*")
            context_lines = tool_args.get("context_lines", 2)
            search_result = search_tools.search(
                query=query,
                scope=scope,
                file_pattern=file_pattern,
                context_lines=context_lines,
            )
            if search_result.error is None:
                log.info(
                    "✅ SEARCH success: %d results from %d files",
                    search_result.total_matches,
                    search_result.files_searched,
                )
                if not search_result.results:
                    return "No results found"
                # Format results for LLM
                formatted = []
                for r in search_result.results[:50]:  # Limit to 50 results
                    formatted.append(f"{r.file_path}:{r.line_number}: {r.line_content}")
                    if r.context:
                        formatted.append(f"  Context:\n{r.context}")
                return f"Found {search_result.total_matches} matches:\n\n" + "\n".join(formatted)
            else:
                log.error("❌ SEARCH failed: %s", search_result.error)
                return f"Error: {search_result.error}"

        else:
            log.error("❌ Unknown tool: %s", tool_name)
            return f"Error: Unknown tool '{tool_name}'"

    except Exception as exc:
        import traceback

        log.error("❌ Tool execution error: %s", exc)
        log.error("%s", traceback.format_exc())
        return f"Error: {type(exc).__name__}: {exc}"


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

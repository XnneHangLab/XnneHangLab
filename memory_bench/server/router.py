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
import hashlib
import json
import time
import uuid
from datetime import UTC
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

    # --- Graph pipeline (Sub-3) ---
    claim_llm_client: OpenAI | None = None  # LLM for claim extraction (can differ from chat)
    claim_llm_model: str = ""  # Model name for claim extraction
    graph_pipeline_enabled: bool = False  # Set True when claim LLM is configured
    neo4j_container: str = "membench-neo4j-mem0"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4jneo4j"

    # --- Metadata nodes ---
    metadata_user_id: str = "xnne"
    metadata_user_name: str = "xnne"
    metadata_agent_id: str = "congyin"
    metadata_agent_name: str = "congyin"
    metadata_scene_id: str = "chill_ai_chat"
    metadata_scene_name: str = "Chill AI Chat"
    metadata_character_id: str = "congyin"
    metadata_character_name: str = "聪音 (Congyin)"


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


# ---------------------------------------------------------------------------
# Metadata nodes (Neo4j)
# ---------------------------------------------------------------------------


def _create_metadata_nodes_cypher() -> str:
    """Generate Cypher to create/update metadata nodes (User, Agent, Scene, Character).

    Node ID format must match offline pipeline (mem0_to_graph.py):
    - user:xnne, agent:congyin, scene:chill_ai_chat
    - char:congyin (NOT character:congyin), char:xnne

    Relationships (matching offline pipeline):
    - Agent -ACTOR→ Character
    - User -USER_IN_SCENE→ Scene
    - Character -IN_SCENE→ Scene (NOT Agent!)
    """
    return f"""
// Create/update User node
MERGE (user:Node {{id: "user:{state.metadata_user_id}"}})
ON CREATE SET user.name = "{state.metadata_user_name}", user.labels = ["User"]
ON MATCH SET user.name = "{state.metadata_user_name}", user.labels = ["User"]

// Create/update Agent node
MERGE (agent:Node {{id: "agent:{state.metadata_agent_id}"}})
ON CREATE SET agent.name = "{state.metadata_agent_name}", agent.labels = ["Agent"]
ON MATCH SET agent.name = "{state.metadata_agent_name}", agent.labels = ["Agent"]

// Create/update Scene node
MERGE (scene:Node {{id: "scene:{state.metadata_scene_id}"}})
ON CREATE SET scene.name = "{state.metadata_scene_name}", scene.labels = ["Scene"]
ON MATCH SET scene.name = "{state.metadata_scene_name}", scene.labels = ["Scene"]

// Create/update Character node (Agent's character) - NOTE: char: prefix (NOT character:)
MERGE (character:Node {{id: "char:{state.metadata_character_id}"}})
ON CREATE SET character.name = "{state.metadata_character_name}", character.labels = ["Character"]
ON MATCH SET character.name = "{state.metadata_character_name}", character.labels = ["Character"]

// Create User's Character node (for user-owned memories) - NOTE: char: prefix
MERGE (user_char:Node {{id: "char:{state.metadata_user_id}"}})
ON CREATE SET user_char.name = "{state.metadata_user_name}", user_char.labels = ["Character"]
ON MATCH SET user_char.name = "{state.metadata_user_name}", user_char.labels = ["Character"]

// Create Agent-Character relationship
MERGE (agent)-[:ACTOR]->(character)

// Create User-Scene relationship
MERGE (user)-[:USER_IN_SCENE]->(scene)

// Create Character-Scene relationship (NOT Agent!)
MERGE (character)-[:IN_SCENE]->(scene)
MERGE (user_char)-[:IN_SCENE]->(scene)
"""


def _run_cypher(
    cypher_text: str,
    *,
    container: str = state.neo4j_container,
    user: str = state.neo4j_user,
    password: str = state.neo4j_password,
) -> tuple[bool, str]:
    """Pipe cypher_text into cypher-shell inside the Neo4j container."""
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        return False, "docker command not found"

    cmd = [
        "docker",
        "exec",
        "-i",
        container,
        "cypher-shell",
        "-u",
        user,
        "-p",
        password,
    ]

    result = subprocess.run(
        cmd,
        input=cypher_text.encode("utf-8"),
        capture_output=True,
        check=False,
        timeout=30,
    )

    if result.returncode == 0:
        return True, ""

    stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
    stdout = (result.stdout or b"").decode("utf-8", errors="replace").strip()
    msg = stderr or stdout or f"exit code {result.returncode}"
    return False, msg


def init_metadata_nodes() -> None:
    """Create/update metadata nodes in Neo4j at server startup."""
    if not state.graph_pipeline_enabled:
        return

    log = logger.bind(group="metadata")
    log.info("Initializing metadata nodes...")

    cypher = _create_metadata_nodes_cypher()
    ok, err = _run_cypher(cypher)

    if ok:
        log.info("✅ Metadata nodes initialized")
    else:
        log.warning("⚠️  Failed to initialize metadata nodes: %s", err)


def create_memory_item_node(memory_id: str, memory_text: str) -> None:
    """Create MemoryItem node and link to User/Agent/Scene/Character."""
    if not state.graph_pipeline_enabled:
        return

    log = logger.bind(group="metadata")

    # Generate a unique ID for this memory item
    import hashlib

    memory_key = hashlib.sha256(memory_text.encode()).hexdigest()[:12]
    node_id = f"mem:{memory_key}"

    cypher = f"""
// Create MemoryItem node
MERGE (mem:Node {{id: "{node_id}"}})
ON CREATE SET mem.labels = ["MemoryItem"], mem.text = "{memory_text[:200].replace(chr(34), chr(92) + chr(34))}"
ON MATCH SET mem.text = "{memory_text[:200].replace(chr(34), chr(92) + chr(34))}"

// Link to metadata nodes
MATCH (user:Node {{id: "user:{state.metadata_user_id}"}})
MATCH (agent:Node {{id: "agent:{state.metadata_agent_id}"}})
MATCH (scene:Node {{id: "scene:{state.metadata_scene_id}"}})
MATCH (character:Node {{id: "character:{state.metadata_character_id}"}})

MERGE (user)-[:OWNS_MEMORY]->(mem)
MERGE (agent)-[:TARGETS_AGENT]->(mem)
MERGE (mem)-[:IN_SCENE]->(scene)
MERGE (mem)-[:HAS_CHARACTER]->(character)
MERGE (mem)-[:FROM_CONV]->(agent)
"""

    ok, err = _run_cypher(cypher)
    if ok:
        log.info("✅ MemoryItem created: %s", node_id)
    else:
        log.warning("⚠️  Failed to create MemoryItem: %s", err)


def _determine_owner(mem0_item: dict[str, Any], memory_text: str) -> str:
    """Determine which character owns this memory.

    Strategy: Check memory text prefix to determine owner.
    - "[User] ..." → User's character (char:xnne)
    - "[Agent] ..." → Agent's character (char:congyin)
    - No prefix → Fallback to Agent's character

    Returns:
        character_id: The character ID (without prefix, e.g., "xnne" or "congyin")
    """
    # Check if memory has [User] or [Agent] prefix
    if memory_text.startswith("[User]"):
        # User's memory → return user's character ID
        return state.user_id  # "xnne" → char:xnne
    elif memory_text.startswith("[Agent]"):
        # Agent's memory → return agent's character ID
        return state.metadata_character_id  # "congyin" → char:congyin
    else:
        # No prefix → fallback to Agent's character (consistent with offline pipeline)
        return state.metadata_character_id


def create_memory_item_node_v2(mem0_item: dict[str, Any], memory_text: str) -> None:
    """Create MemoryItem node and link to Character (owner) + Scene + Conversation.

    Node properties are aligned with the offline pipeline (mem0_to_graph.py)
    so that online and offline MemoryItem nodes share the same schema.

    Args:
        mem0_item: Full mem0 result item (for owner detection, includes ``id`` = point UUID)
        memory_text: The memory text content
    """
    if not state.graph_pipeline_enabled:
        return

    log = logger.bind(group="metadata")

    # --- MemoryItem properties (aligned with offline pipeline) ---
    from datetime import datetime, timezone

    payload_hash = hashlib.md5(memory_text.encode()).hexdigest()
    node_id = f"mem:{payload_hash}"
    display_name = f"{memory_text} #{payload_hash[:8]}"
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")  # noqa: UP017
    point_id = mem0_item.get("id", "")  # mem0 UUID

    # Determine owner character
    owner_character_id = _determine_owner(mem0_item, memory_text)
    log.info("🎯 Memory owner: %s (for: %s)", owner_character_id, memory_text[:50])

    # Generate conversation ID from current date (e.g., "2026-02-27")
    conv_id = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # noqa: UP017
    conv_node_id = f"conv:{conv_id}"

    log.info("💬 Conversation: %s", conv_node_id)

    # Escape double-quotes for Cypher string literals
    _esc_data = memory_text.replace("\\", "\\\\").replace('"', '\\"')
    _esc_display = display_name.replace("\\", "\\\\").replace('"', '\\"')

    cypher = f"""
// Create MemoryItem node (properties aligned with offline pipeline)
MERGE (mem:Node {{id: "{node_id}"}})
ON CREATE SET
  mem.labels = ["MemoryItem"],
  mem.data = "{_esc_data}",
  mem.payload_hash = "{payload_hash}",
  mem.display = "{_esc_display}",
  mem.name = "{_esc_display}",
  mem.created_at = "{now_iso}",
  mem.point_id = "{point_id}",
  mem.isolation = "global",
  mem.collection = "memory_bench_global",
  mem.exported_at = "{now_iso}"
ON MATCH SET
  mem.data = "{_esc_data}",
  mem.payload_hash = "{payload_hash}",
  mem.display = "{_esc_display}",
  mem.name = "{_esc_display}",
  mem.point_id = "{point_id}",
  mem.isolation = "global",
  mem.collection = "memory_bench_global",
  mem.exported_at = "{now_iso}"

// Create Conversation node (by date)
MERGE (conv:Node {{id: "{conv_node_id}"}})
ON CREATE SET
  conv.labels = ["Conversation"],
  conv.conv_id = "{conv_id}",
  conv.display = "{conv_id}",
  conv.name = "{conv_id}"
ON MATCH SET
  conv.labels = ["Conversation"],
  conv.conv_id = "{conv_id}",
  conv.display = "{conv_id}",
  conv.name = "{conv_id}"

// Link to owner Character (NOTE: char: prefix)
WITH mem, conv
MATCH (owner:Node {{id: "char:{owner_character_id}"}})
MERGE (owner)-[:OWNS_MEMORY]->(mem)

// Link to Scene
WITH mem, owner
MATCH (scene:Node {{id: "scene:{state.metadata_scene_id}"}})
MERGE (mem)-[:IN_SCENE]->(scene)

// Link to owner Character (HAS_CHARACTER)
MERGE (mem)-[:HAS_CHARACTER]->(owner)

// Link to Conversation (FROM_CONV)
MERGE (mem)-[:FROM_CONV]->(conv)

// Link Conversation to Scene and Character
MERGE (conv)-[:CONV_IN_SCENE]->(scene)
MERGE (conv)-[:CONV_HAS_CHARACTER]->(owner)
"""

    ok, err = _run_cypher(cypher)
    if ok:
        log.info("✅ MemoryItem created: %s (owner: %s, conv: %s)", node_id, owner_character_id, conv_id)
    else:
        log.warning("⚠️  Failed to create MemoryItem: %s", err)


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


def _add_memory_sync(user_msg: str, assistant_msg: str) -> list[dict[str, Any]]:
    """Write user+assistant turn to mem0 (no system prompt).

    Returns the ``results`` list from ``mem0.add()`` so the graph pipeline
    can extract claims from the newly stored memories.
    """
    if state.mem0 is None:
        return []
    log = logger.bind(group="server")
    try:
        result = state.mem0.add(
            messages=[
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ],
            user_id=state.user_id,
            agent_id=state.agent_id,
            metadata={"scene_id": "chill_ai_chat", "character_id": state.agent_id},
        )
        # Log what mem0 actually stored
        results = result.get("results", []) if isinstance(result, dict) else []
        if results:
            for item in results:
                event = item.get("event", "unknown")
                memory_text = item.get("memory", "")
                # DEBUG: 打印完整结构，帮助判断 owner
                log.info("\U0001f4be mem0 %s: %s", event, memory_text[:150])
                log.info("\U0001f50d DEBUG mem0 item keys: %s", list(item.keys()))
                log.info("\U0001f50d DEBUG mem0 item full: %s", json.dumps(item, indent=2)[:500])
                # Create MemoryItem node for each new memory
                if event == "ADD" and memory_text:
                    create_memory_item_node_v2(item, memory_text)
        else:
            log.info("\U0001f4be mem0 returned no new memory items")
        return results
    except Exception as exc:
        log.error("\u274c Failed to add memory: %s", exc)
        return []


def _graph_pipeline_sync(mem0_results: list[dict[str, Any]]) -> None:
    """Extract claims from mem0 results and write to Neo4j.

    This runs the full graph pipeline:
    1. ``claim_extractor.extract_claims()`` — LLM-based claim/entity extraction
    2. ``graph_writer.write_to_neo4j()`` — Cypher MERGE into Neo4j

    Graceful degradation: any failure is logged but never raised.
    """
    if not state.graph_pipeline_enabled:
        return
    if not mem0_results:
        return

    log = logger.bind(group="graph")

    # Lazy imports to avoid circular deps and keep startup fast
    from memory_bench.server.claim_extractor import extract_claims
    from memory_bench.server.graph_writer import write_to_neo4j

    try:
        # Step 1: Extract claims
        records = extract_claims(
            openai_client=state.claim_llm_client,
            model=state.claim_llm_model,
            mem0_results=mem0_results,
            scene_id="chill_ai_chat",
            agent_id=state.agent_id,
            user_id=state.user_id,
        )
        if not records:
            log.info("\U0001f4ad No claims extracted from %d mem0 results", len(mem0_results))
            return

        log.info("\U0001f4a1 Extracted %d claim/entity records", len(records))

        # Step 2: Write to Neo4j
        result = write_to_neo4j(
            claim_records=records,
            user_id=state.user_id,
            container=state.neo4j_container,
            neo4j_user=state.neo4j_user,
            neo4j_password=state.neo4j_password,
        )
        log.info(
            "\U0001f4ca Graph write: %d nodes, %d edges (skipped: %d nodes, %d edges, ok=%s)",
            result.nodes_written,
            result.edges_written,
            result.nodes_skipped,
            result.edges_skipped,
            result.cypher_ok,
        )
        if not result.cypher_ok:
            log.warning("\u26a0\ufe0f Cypher execution error: %s", result.error)
    except Exception as exc:
        log.error("\u274c Graph pipeline failed: %s", exc)


async def _memory_and_graph_background(user_msg: str, assistant_msg: str) -> None:
    """Background task: mem0 write-back (sync) → graph pipeline (async).

    mem0.add() is synchronous and must complete before graph pipeline starts
    (it needs the results).  Both run in a thread executor to avoid blocking
    the event loop.
    """
    loop = asyncio.get_running_loop()
    # Step 1: mem0 write-back (synchronous, returns results)
    mem0_results = await loop.run_in_executor(None, _add_memory_sync, user_msg, assistant_msg)
    # Step 2: graph pipeline (synchronous, uses mem0 results)
    if mem0_results and state.graph_pipeline_enabled:
        await loop.run_in_executor(None, _graph_pipeline_sync, mem0_results)


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

    log = logger.bind(group="server")

    # 1. Latest user message
    user_messages = [m for m in request.messages if m.role == "user"]
    latest_user_msg = user_messages[-1].content if user_messages else ""

    # 2. Memory search
    memories = _search_memories(latest_user_msg) if latest_user_msg else []
    memories_text = _format_memories(memories)
    if memories:
        log.info("\U0001f50d Found %d memories for user query", len(memories))
        for rank, mem in enumerate(memories[:2], 1):
            text = mem.get("memory", "") or mem.get("data", "") or str(mem)
            score = mem.get("score", "")
            score_str = f" (score: {score:.2f})" if isinstance(score, float) else ""
            log.info("   top%d: %s%s", rank, text[:120], score_str)

    # 3. Inject
    augmented = _inject_memories(request.messages, memories_text)

    # 4. Forward to LLM
    model = request.model or state.chat_model
    log.info("\U0001f4e4 Forwarding to LLM: %s (tokens: max=%d)", model, request.max_tokens or 2000)
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

        log.error("\u274c LLM provider error: %s", exc)
        log.error("%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail=f"LLM provider error: {type(exc).__name__}: {exc}") from exc

    assistant_content = completion.choices[0].message.content or ""

    # 5. Async write-back + graph pipeline (user + assistant only, no system prompt)
    if latest_user_msg and assistant_content:
        log.info("\U0001f4be Queued memory write-back + graph pipeline (async)")
        asyncio.create_task(_memory_and_graph_background(latest_user_msg, assistant_content))

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
            "graph_pipeline_enabled": state.graph_pipeline_enabled,
            "claim_llm_model": state.claim_llm_model or None,
        }
    )

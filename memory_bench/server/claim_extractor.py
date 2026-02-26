"""Realtime claim extractor — extract claims/entities from mem0 memory items.

This module is the realtime counterpart of ``claimify_all.py``.  While
``claimify_all`` operates on full mem0 export JSONL files in batch mode,
this extractor works on the lightweight ``results`` returned by
``mem0.add()`` during live chat, producing claim/entity records that
can be written directly to Neo4j.

Design decisions
----------------
- **Simplified prompt**: The batch prompt (``23_CLAIM_EXTRACTOR_PROMPT.md``)
  expects full export JSONL with ``point_id`` / ``hash`` / ``conv_id`` etc.
  The realtime prompt only receives memory text + metadata, keeping the LLM
  call fast and cheap.
- **Graceful degradation**: If the LLM returns empty / malformed output, we
  log a warning and return an empty list — the chat response is never blocked.
- **No tag registry**: The batch pipeline maintains a tag registry for cross-
  conv deduplication.  In realtime mode we skip this (minor duplication is
  acceptable; the batch pipeline can reconcile later).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from memory_bench.scripts.bench_logger import logger

# ---------------------------------------------------------------------------
# Allowed values (subset of claimify_all.py constants)
# ---------------------------------------------------------------------------

ALLOWED_RECORD_TYPES = {"entity", "claim"}
ALLOWED_ENTITY_TYPES = {"Agent", "User", "Author", "Work", "Chapter", "Topic", "Tag"}
ALLOWED_PREDICATES = {
    "PREFERS_AUTHOR",
    "FAVORITE_WORK",
    "DISCUSSED_WORK",
    "DISCUSSED_CHAPTER",
    "PREFERS_NARRATIVE_STYLE",
    "SELF_TRAIT",
    "TRIED_STYLE",
    "SELF_CRITIQUE",
    "PREFERS_TOPIC",
}
ALLOWED_DOMAINS = {"reading", "writing", "daily"}

# ---------------------------------------------------------------------------
# Prompt template for realtime extraction
# ---------------------------------------------------------------------------

_REALTIME_CLAIM_PROMPT = """\
You are a Memory Claim Extractor.  Given a list of memory items (short text
snippets stored by an AI assistant about its user), extract structured
claim/entity records for a knowledge graph.

## Rules
- Output strict JSONL only (one JSON object per line, no markdown, no explanation).
- Each line must have ``record_type``: either ``"entity"`` or ``"claim"``.
- Only use these predicates: {predicates}
- Only use these entity types: {entity_types}
- Only use these domains: reading, writing, daily
- ``claim_id`` format: ``claim:{{predicate}}|{{domain}}|{{subject.entity_id}}|{{object.entity_id}}``
- Each claim must include an ``evidence`` array with at least one item containing
  ``memory_item_id``, ``text``, ``scene_id``, and ``created_at``.
- ``confidence`` must be 0.0–1.0.  Do not output claims below 0.6.
- If no claims can be extracted, output nothing (empty response is OK).

## Entity ID rules
- Agent: ``agent:<id>``  (e.g. ``agent:congyin``)
- User: ``user:<id>``  (e.g. ``user:xnne``)
- Author: ``author:<name>``
- Work: ``work:<title>``  (strip 《》)
- Topic: ``topic:<name>``
- Tag: ``tag:<short_phrase>``  (strip context words like 觉得/读起来)

## Input
scene_id={scene_id}
character_id={character_id}
agent_id={agent_id}
user_id={user_id}

Memory items:
{memory_items}

## Output (JSONL only)
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _memory_hash(text: str) -> str:
    """Deterministic hash for a memory text (mirrors mem0 payload.hash idea)."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")  # noqa: UP017


def _strip_codefence(text: str) -> str:
    """Remove markdown code fences wrapping LLM output."""
    pattern = re.compile(r"```(?:\w*)?\n(.*?)```", re.DOTALL)
    matches = pattern.findall(text)
    if matches:
        return "\n".join(matches).strip()
    return text


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_prompt(
    memory_items: list[dict[str, str]],
    *,
    scene_id: str = "chill_ai_chat",
    character_id: str = "congyin",
    agent_id: str = "congyin",
    user_id: str = "xnne",
) -> str:
    """Build the LLM prompt for realtime claim extraction.

    Parameters
    ----------
    memory_items:
        List of dicts with ``"memory_item_id"``, ``"text"``, and
        ``"created_at"`` keys.
    """
    lines: list[str] = []
    for item in memory_items:
        lines.append(json.dumps(item, ensure_ascii=False))
    items_block = "\n".join(lines)

    return _REALTIME_CLAIM_PROMPT.format(
        predicates=", ".join(sorted(ALLOWED_PREDICATES)),
        entity_types=", ".join(sorted(ALLOWED_ENTITY_TYPES)),
        scene_id=scene_id,
        character_id=character_id,
        agent_id=agent_id,
        user_id=user_id,
        memory_items=items_block,
    )


# ---------------------------------------------------------------------------
# Result parser
# ---------------------------------------------------------------------------


def _validate_entity(obj: dict[str, Any]) -> bool:
    """Return True if entity record has required fields and valid values."""
    if obj.get("entity_type") not in ALLOWED_ENTITY_TYPES:
        return False
    if not isinstance(obj.get("entity_id"), str) or not obj["entity_id"].strip():
        return False
    if not isinstance(obj.get("props"), dict):
        return False
    conf = obj.get("confidence")
    if not isinstance(conf, (int, float)) or not (0 <= float(conf) <= 1):
        return False
    # Ensure aliases and tags are lists
    if not isinstance(obj.get("aliases"), list):
        obj["aliases"] = []
    if not isinstance(obj.get("tags"), list):
        obj["tags"] = []
    return True


def _validate_claim(obj: dict[str, Any]) -> bool:
    """Return True if claim record has required fields and valid values."""
    if obj.get("predicate") not in ALLOWED_PREDICATES:
        return False
    if obj.get("domain") not in ALLOWED_DOMAINS:
        return False
    for side in ("subject", "object"):
        node = obj.get(side)
        if not isinstance(node, dict):
            return False
        if not isinstance(node.get("entity_id"), str) or not node["entity_id"].strip():
            return False
    conf = obj.get("confidence")
    if not isinstance(conf, (int, float)) or not (0 <= float(conf) <= 1):
        return False
    evidence = obj.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return False
    # Recompute canonical claim_id
    subj_id = obj["subject"]["entity_id"]
    obj_id = obj["object"]["entity_id"]
    obj["claim_id"] = f"claim:{obj['predicate']}|{obj['domain']}|{subj_id}|{obj_id}"
    return True


def parse_llm_output(raw: str) -> list[dict[str, Any]]:
    """Parse and validate LLM JSONL output, returning valid records only.

    Invalid lines are silently skipped (logged at debug level).
    """
    log = logger.bind(group="server")
    if not raw or not raw.strip():
        return []

    text = _strip_codefence(raw)
    records: list[dict[str, Any]] = []

    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            log.warning("claim_extractor: skip invalid JSON on line %d", line_no)
            continue
        if not isinstance(obj, dict):
            continue

        rt = obj.get("record_type")
        if rt == "entity":
            if _validate_entity(obj):
                records.append(obj)
        elif rt == "claim":
            if _validate_claim(obj):
                records.append(obj)
        # else: skip unknown record_type

    return records


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------


def prepare_memory_items(
    mem0_results: list[dict[str, Any]],
    *,
    scene_id: str = "chill_ai_chat",
) -> list[dict[str, str]]:
    """Convert mem0.add() results into prompt-ready memory items.

    Parameters
    ----------
    mem0_results:
        The ``results`` list from ``mem0.add()`` return value.
        Each item typically has ``"event"`` (ADD/UPDATE/NOOP) and ``"memory"`` (text).

    Returns
    -------
    list[dict[str, str]]
        Items with ``memory_item_id``, ``text``, ``scene_id``, ``created_at``.
        Only ADD/UPDATE events with non-empty text are included.
    """
    items: list[dict[str, str]] = []
    now = _now_iso()
    for result in mem0_results:
        event = str(result.get("event", "")).upper()
        if event not in ("ADD", "UPDATE"):
            continue
        text = str(result.get("memory", "")).strip()
        if not text:
            continue
        items.append(
            {
                "memory_item_id": f"mem:{_memory_hash(text)}",
                "text": text,
                "scene_id": scene_id,
                "created_at": now,
            }
        )
    return items


def extract_claims(
    openai_client: Any,
    model: str,
    mem0_results: list[dict[str, Any]],
    *,
    scene_id: str = "chill_ai_chat",
    character_id: str = "congyin",
    agent_id: str = "congyin",
    user_id: str = "xnne",
) -> list[dict[str, Any]]:
    """Extract claims/entities from mem0.add() results via LLM.

    This is the main entry point.  It:
    1. Filters mem0 results to actionable items (ADD/UPDATE with text).
    2. Builds a prompt and calls the LLM.
    3. Parses and validates the output.

    Returns an empty list on any failure (never raises).

    Parameters
    ----------
    openai_client:
        An initialized ``openai.OpenAI`` client instance.
    model:
        The model name to use for extraction.
    mem0_results:
        The ``results`` list from ``mem0.add()`` return value.
    """
    log = logger.bind(group="server")

    # 1. Prepare items
    items = prepare_memory_items(mem0_results, scene_id=scene_id)
    if not items:
        log.info("\U0001f4a4 claim_extractor: no actionable memory items, skipping")
        return []

    # 2. Build prompt
    prompt = build_prompt(
        items,
        scene_id=scene_id,
        character_id=character_id,
        agent_id=agent_id,
        user_id=user_id,
    )

    # 3. Call LLM
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_completion_tokens=4000,
        )
        raw_output = response.choices[0].message.content or ""
    except Exception as exc:
        log.error("\u274c claim_extractor LLM call failed: %s", exc)
        return []

    # 4. Parse
    records = parse_llm_output(raw_output)
    entities = [r for r in records if r.get("record_type") == "entity"]
    claims = [r for r in records if r.get("record_type") == "claim"]
    log.info(
        "\U0001f4ca claim_extractor: extracted %d entities + %d claims from %d memory items",
        len(entities),
        len(claims),
        len(items),
    )
    return records

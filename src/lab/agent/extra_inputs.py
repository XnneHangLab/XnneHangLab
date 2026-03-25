from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from lab.tools.types import AgentContext

InjectionMode = Literal["soft", "hard"]
_CORE_EXTRA_INPUT_QUEUE_KEY = "core_extra_inputs"


class CoreExtraInputKind(str, Enum):
    SCREEN_OBSERVATION = "screen_observation"
    SCREEN_STATE_SUMMARY_UPDATE = "screen_state_summary_update"


@dataclass(slots=True)
class CoreExtraInput:
    """A system-side extra input item queued for AgentCore consumption."""

    kind: CoreExtraInputKind
    source: str
    injection_mode: InjectionMode
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _get_or_create_queue(ctx: AgentContext) -> list[CoreExtraInput]:
    raw_queue = ctx.extra.get(_CORE_EXTRA_INPUT_QUEUE_KEY)
    if isinstance(raw_queue, list):
        # Keep only valid items to avoid leaking malformed data into prompt context.
        queue = [item for item in raw_queue if isinstance(item, CoreExtraInput)]
        if len(queue) != len(raw_queue):
            ctx.extra[_CORE_EXTRA_INPUT_QUEUE_KEY] = queue
        return queue

    queue: list[CoreExtraInput] = []
    ctx.extra[_CORE_EXTRA_INPUT_QUEUE_KEY] = queue
    return queue


def push_core_extra_input(ctx: AgentContext, entry: CoreExtraInput) -> None:
    queue = _get_or_create_queue(ctx)
    queue.append(entry)


def consume_core_extra_inputs(ctx: AgentContext) -> list[CoreExtraInput]:
    queue = _get_or_create_queue(ctx)
    consumed = list(queue)
    queue.clear()
    return consumed


def inject_screen_state_summary_update(
    ctx: AgentContext,
    *,
    summary_text: str,
    summary_hash: str,
    importance: str,
    reasons: list[str],
    injection_mode: InjectionMode,
    evidence_capture_id: str | None = None,
    scene: str | None = None,
    app_name: str | None = None,
    window_title: str | None = None,
) -> CoreExtraInput:
    payload = {
        "summary_text": summary_text,
        "summary_hash": summary_hash,
        "importance": importance,
        "reasons": reasons,
        "evidence_capture_id": evidence_capture_id,
        "scene": scene,
        "app_name": app_name,
        "window_title": window_title,
    }
    event = CoreExtraInput(
        kind=CoreExtraInputKind.SCREEN_STATE_SUMMARY_UPDATE,
        source="screen_state_observer",
        injection_mode=injection_mode,
        payload=payload,
    )
    push_core_extra_input(ctx, event)
    return event


def _compact_line(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    return " ".join(text.split())


def render_core_extra_inputs_context(entries: list[CoreExtraInput]) -> str | None:
    if not entries:
        return None

    lines = ["[System Observation Context]"]
    for entry in entries:
        payload = entry.payload
        summary = _compact_line(payload.get("summary_text", ""))
        importance = _compact_line(payload.get("importance", "unknown"))
        reason_list = payload.get("reasons")
        reasons = ", ".join(str(item).strip() for item in reason_list if str(item).strip()) if isinstance(reason_list, list) else ""
        summary_hash = _compact_line(payload.get("summary_hash", ""))
        capture_id = _compact_line(payload.get("evidence_capture_id", ""))
        mode_tag = entry.injection_mode.upper()
        kind = entry.kind.value
        timestamp = entry.created_at.isoformat()

        lines.append(
            f"- [{mode_tag}] kind={kind} source={entry.source} at={timestamp} importance={importance}"
            + (f" capture={capture_id}" if capture_id else "")
            + (f" hash={summary_hash}" if summary_hash else "")
        )
        if summary:
            lines.append(f"  summary: {summary}")
        if reasons:
            lines.append(f"  reasons: {reasons}")

    return "\n".join(lines)

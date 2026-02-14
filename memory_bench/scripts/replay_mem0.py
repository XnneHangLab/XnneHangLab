#!/usr/bin/env python3
"""Replay memory bench events against Mem0 and log probe retrieval metrics."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bench_logger import logger


class ReplayMem0Error(RuntimeError):
    """Raised when replay input/config is invalid."""


@dataclass(slots=True)
class ReplayStats:
    total_events: int = 0
    ingested_events: int = 0
    skipped_events: int = 0
    probe_events: int = 0


def parse_csv_arg(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(",") if part.strip()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay benchmark events against Mem0")
    parser.add_argument(
        "--input",
        type=str,
        default="memory_bench/data/events/compiled/all.jsonl",
        help="Input event JSONL, e.g. compiled/all.jsonl or by_chapter/chXX.jsonl",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional output log JSONL path. Defaults to logs/replay_mem0/run_YYYYMMDD_HHMM.jsonl",
    )
    parser.add_argument(
        "--isolation",
        choices=["per_chapter", "global"],
        default="global",
        help="Mem0 user isolation mode",
    )
    parser.add_argument("--k", type=int, default=5, help="Top-k for probe retrieval")
    parser.add_argument(
        "--skip-role",
        type=str,
        default="ui,tool",
        help="Comma separated role_type values to skip",
    )
    parser.add_argument(
        "--skip-tags",
        type=str,
        default="filler",
        help="Comma separated tags. If event has any, skip ingest",
    )
    parser.add_argument(
        "--only-tags",
        type=str,
        default="",
        help="Optional allow-list tags. If set, events must include at least one listed tag to ingest",
    )
    parser.add_argument(
        "--write-probes",
        action="store_true",
        help="Write probe events into Mem0 (default: false)",
    )
    return parser.parse_args()


def to_mem0_message(role_type: str, content: str) -> dict[str, str] | None:
    if role_type == "human":
        return {"role": "user", "content": content}
    if role_type == "assistant":
        return {"role": "assistant", "content": content}
    return None


def build_user_id(event: dict[str, Any], isolation: str) -> str:
    scene_id = str(event.get("scene_id", "")).strip()
    character_id = str(event.get("character_id", "")).strip()
    conv_id = str(event.get("conv_id", "")).strip()
    if not scene_id or not character_id:
        raise ReplayMem0Error("event missing scene_id/character_id")
    if isolation == "global":
        return f"{scene_id}:{character_id}"
    if not conv_id:
        raise ReplayMem0Error("event missing conv_id for per_chapter isolation")
    return f"{scene_id}:{character_id}:{conv_id}"


def should_ingest(
    event: dict[str, Any],
    skip_roles: set[str],
    skip_tags: set[str],
    only_tags: set[str],
    write_probes: bool,
) -> bool:
    role_type = str(event.get("role_type", "")).strip()
    content = str(event.get("content", "")).strip()
    tags_raw = event.get("tags", [])
    tags = {str(tag) for tag in tags_raw} if isinstance(tags_raw, list) else set()

    if not content:
        return False
    if role_type not in {"human", "assistant"}:
        return False
    if role_type in skip_roles:
        return False
    if skip_tags and tags.intersection(skip_tags):
        return False
    if only_tags and not tags.intersection(only_tags):
        return False
    if ("probe" in tags) and (not write_probes):
        return False
    return True


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ReplayMem0Error(f"input file not found: {path}")

    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                logger.bind(group="memory").warning(f"skip empty line in input JSONL: {path} (line {i})")
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ReplayMem0Error(f"invalid JSON on line {i}: {exc}") from exc
            if not isinstance(obj, dict):
                raise ReplayMem0Error(f"event line {i} must be JSON object")
            events.append(obj)
    return events


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    return Path(f"memory_bench/logs/replay_mem0/run_{timestamp}.jsonl")


def compact_hits_preview(hits: Any, k: int) -> list[dict[str, Any]]:
    if not isinstance(hits, list):
        return []
    preview: list[dict[str, Any]] = []
    for hit in hits[:k]:
        if not isinstance(hit, dict):
            continue
        content = str(hit.get("memory", "") or hit.get("content", ""))
        metadata = hit.get("metadata", {})
        score = hit.get("score")
        preview.append({"content": content[:160], "score": score, "metadata": metadata})
    return preview


def main() -> int:
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    skip_roles = parse_csv_arg(args.skip_role)
    skip_tags = parse_csv_arg(args.skip_tags)
    only_tags = parse_csv_arg(args.only_tags)

    try:
        from mem0 import Memory
    except ImportError as exc:
        raise ReplayMem0Error(
            "mem0 is not installed. Install dependency group `memory_bench` first, e.g. `uv sync --group memory_bench`."
        ) from exc

    events = read_jsonl(input_path)
    stats = ReplayStats()

    logger.bind(group="memory").info(
        f"Replay start: input={input_path}, output={output_path}, isolation={args.isolation}, k={args.k}"
    )

    memory = Memory()
    with output_path.open("w", encoding="utf-8") as out_file:
        for event in events:
            stats.total_events += 1
            tags_raw = event.get("tags", [])
            tags = {str(tag) for tag in tags_raw} if isinstance(tags_raw, list) else set()

            user_id = build_user_id(event, args.isolation)

            if "probe" in tags:
                stats.probe_events += 1
                query = str(event.get("content", "")).strip()
                started = time.perf_counter()
                result = memory.search(query=query, user_id=user_id, limit=args.k)
                latency_ms = round((time.perf_counter() - started) * 1000, 3)

                if isinstance(result, list):
                    hits = result
                elif isinstance(result, dict):
                    hits_any = result.get("results") or result.get("memories") or []
                    hits = hits_any if isinstance(hits_any, list) else []
                else:
                    hits = []

                log_record = {
                    "backend": "mem0",
                    "conv_id": event.get("conv_id"),
                    "turn_id": event.get("turn_id"),
                    "scene_id": event.get("scene_id"),
                    "character_id": event.get("character_id"),
                    "probe_query": query,
                    "hits_count": len(hits),
                    "hits_preview": compact_hits_preview(hits, args.k),
                    "latency_ms": latency_ms,
                }
                out_file.write(json.dumps(log_record, ensure_ascii=False) + "\n")

            if should_ingest(event, skip_roles, skip_tags, only_tags, args.write_probes):
                role_type = str(event.get("role_type", "")).strip()
                content = str(event.get("content", "")).strip()
                message = to_mem0_message(role_type, content)
                if message is None:
                    stats.skipped_events += 1
                    continue
                memory.add(messages=[message], user_id=user_id)
                stats.ingested_events += 1
            else:
                stats.skipped_events += 1

    logger.bind(group="memory").info(
        "Replay done: "
        f"events={stats.total_events}, ingested={stats.ingested_events}, skipped={stats.skipped_events}, "
        f"probes={stats.probe_events}, log={output_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReplayMem0Error as exc:
        logger.bind(group="memory").warning(str(exc))
        raise SystemExit(1) from exc

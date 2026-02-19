#!/usr/bin/env python3
"""Tag registry utilities for canonicalization and candidate selection."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

PREFIXES = [
    "在写作中",
    "寫起來",
    "写起来",
    "读起来",
    "寫作",
    "写作",
    "看起来",
    "覺得",
    "觉得",
    "自认为",
    "自認為",
    "可能",
    "有点",
    "有點",
    "比较",
    "比較",
]

QUOTE_CHARS = "《》“”\"''"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_tag_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "updated_at": _now_iso(), "tags": []}

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"version": 1, "updated_at": _now_iso(), "tags": []}
    tags = data.get("tags")
    if not isinstance(tags, list):
        data["tags"] = []
    data.setdefault("version", 1)
    data.setdefault("updated_at", _now_iso())
    return data


def save_tag_registry(path: Path, registry_dict: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    registry_dict["updated_at"] = _now_iso()
    path.write_text(json.dumps(registry_dict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_tag_name(name: str) -> str:
    value = str(name or "")
    for ch in QUOTE_CHARS:
        value = value.replace(ch, "")
    value = value.strip()

    changed = True
    while changed and value:
        changed = False
        for prefix in PREFIXES:
            if value.startswith(prefix):
                value = value[len(prefix) :].strip()
                changed = True

    value = re.sub(r"\s+", " ", value).strip()
    return value


def canonical_tag_id(name: str) -> str:
    normalized = normalize_tag_name(name)
    return f"tag:{normalized}"


def update_registry_from_records(registry: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    tags = registry.setdefault("tags", [])
    tag_by_id = {
        str(item.get("tag_id")): item
        for item in tags
        if isinstance(item, dict) and isinstance(item.get("tag_id"), str)
    }
    now = _now_iso()

    for obj in records:
        if obj.get("record_type") != "entity" or obj.get("entity_type") != "Tag":
            continue
        props = obj.get("props") if isinstance(obj.get("props"), dict) else {}
        raw_name = props.get("name") or props.get("display") or obj.get("entity_id", "")
        if isinstance(raw_name, str) and raw_name.startswith("tag:"):
            raw_name = raw_name[4:]
        name = normalize_tag_name(str(raw_name))
        if not name:
            continue

        tag_id = canonical_tag_id(name)
        entry = tag_by_id.get(tag_id)
        if not entry:
            entry = {
                "tag_id": tag_id,
                "name": name,
                "count": 0,
                "first_seen_at": now,
                "last_seen_at": now,
            }
            tags.append(entry)
            tag_by_id[tag_id] = entry

        entry["name"] = name
        entry["count"] = int(entry.get("count", 0)) + 1
        entry.setdefault("first_seen_at", now)
        entry["last_seen_at"] = now

    tags.sort(key=lambda item: str(item.get("tag_id", "")))
    return registry


def select_topk_tags_for_chunk(registry: dict[str, Any], chunk_text: str, k: int = 20) -> list[dict[str, Any]]:
    tags = registry.get("tags") if isinstance(registry, dict) else []
    if not isinstance(tags, list):
        return []

    text = chunk_text or ""
    text_l = text.lower()
    text_window = text_l[:4000]

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for item in tags:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        tag_id = str(item.get("tag_id", "")).strip()
        if not name or not tag_id:
            continue

        name_l = name.lower()
        if name_l and name_l in text_l:
            score = 100.0 + min(20.0, len(name_l) / 10)
        else:
            score = SequenceMatcher(None, name_l, text_window).ratio() * 10

        count = int(item.get("count", 0))
        scored.append((score, count, {"tag_id": tag_id, "name": name}))

    scored.sort(key=lambda row: (-row[0], -row[1], row[2]["tag_id"]))
    return [row[2] for row in scored[:k]]

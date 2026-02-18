"""Entity registry helpers (PR1 minimal implementation)."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone


_FULLWIDTH_SPACE = "\u3000"

# 常见中英文符号、引号、括号、书名号等。
_REMOVE_CHARS = {
    " ",
    _FULLWIDTH_SPACE,
    "\t",
    "\n",
    "\r",
    ",",
    "，",
    ".",
    "。",
    "!",
    "！",
    "?",
    "？",
    ":",
    "：",
    ";",
    "；",
    "-",
    "—",
    "_",
    "~",
    "～",
    "·",
    "…",
    "'",
    '"',
    "“",
    "”",
    "‘",
    "’",
    "`",
    "『",
    "』",
    "「",
    "」",
    "《",
    "》",
    "(",
    ")",
    "（",
    "）",
    "[",
    "]",
    "【",
    "】",
    "{",
    "}",
    "<",
    ">",
}


def _to_halfwidth_ascii(text: str) -> str:
    """Convert fullwidth ASCII variants to halfwidth."""

    converted: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            converted.append(chr(code - 0xFEE0))
        elif ch == _FULLWIDTH_SPACE:
            converted.append(" ")
        else:
            converted.append(ch)
    return "".join(converted)


def normalize_name(name: str) -> str:
    """Normalize entity name for deterministic matching."""

    normalized = _to_halfwidth_ascii(name)
    normalized = normalized.lower()
    normalized = "".join(ch for ch in normalized if ch not in _REMOVE_CHARS)
    return normalized


def ensure_entities_tables(conn: sqlite3.Connection) -> None:
    """Create PR1 minimal entities table and index if missing."""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entities (
            entity_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            normalized TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(type, normalized)
        )
        """
    )


def _stable_entity_id(entity_type: str, normalized: str) -> str:
    digest = hashlib.sha1(f"{entity_type}:{normalized}".encode("utf-8")).hexdigest()[:32]
    return f"ent:{entity_type}:{digest}"


def resolve_entity(
    conn: sqlite3.Connection,
    type: str,
    name: str,
    *,
    create: bool = True,
) -> str | None:
    """Resolve or create entity by exact (type, normalized) match."""

    ensure_entities_tables(conn)

    if not isinstance(name, str):
        return None

    normalized = normalize_name(name)
    if not normalized:
        return None

    row = conn.execute(
        "SELECT entity_id FROM entities WHERE type = ? AND normalized = ?",
        (type, normalized),
    ).fetchone()
    if row:
        return str(row[0])

    if not create:
        return None

    entity_id = _stable_entity_id(type, normalized)
    created_at = datetime.now(timezone.utc).isoformat()

    try:
        conn.execute(
            """
            INSERT INTO entities (entity_id, type, name, normalized, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_id, type, name, normalized, created_at),
        )
    except sqlite3.IntegrityError:
        row = conn.execute(
            "SELECT entity_id FROM entities WHERE type = ? AND normalized = ?",
            (type, normalized),
        ).fetchone()
        return str(row[0]) if row else None

    return entity_id

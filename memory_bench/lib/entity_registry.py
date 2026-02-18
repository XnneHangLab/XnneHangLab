"""实体注册表工具（PR1 最小实现）。

该模块提供实体名归一化、基础表结构初始化与基于 `(type, normalized)`
精确匹配的实体解析/创建能力，不包含 aliases 相关逻辑。
"""

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
    """将全角 ASCII 变体转换为半角字符。

    Args:
        text: 原始输入字符串。

    Returns:
        转换后的字符串。
    """

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
    """对实体名做稳定归一化处理。

    处理规则包括：全角 ASCII 转半角、拉丁字母小写化、去除空白与常见中英文标点。

    Args:
        name: 待归一化名称；若不是字符串则返回空字符串。

    Returns:
        归一化后的名称；若输入无效或归一化后为空可能返回空字符串。
    """

    if not isinstance(name, str):
        return ""

    normalized = _to_halfwidth_ascii(name)
    normalized = normalized.lower()
    normalized = "".join(ch for ch in normalized if ch not in _REMOVE_CHARS)
    return normalized


def ensure_entities_tables(conn: sqlite3.Connection) -> None:
    """确保 PR1 所需的 entities 表存在。

    Args:
        conn: SQLite 连接对象。
    """

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
    """根据实体类型与归一化名称生成稳定实体 ID。

    Args:
        entity_type: 实体类型。
        normalized: 归一化名称。

    Returns:
        稳定的实体 ID，格式为 `ent:{type}:{hash}`。
    """

    digest = hashlib.sha1(f"{entity_type}:{normalized}".encode()).hexdigest()[:32]
    return f"ent:{entity_type}:{digest}"


def resolve_entity(
    conn: sqlite3.Connection,
    type: str,
    name: str,
    *,
    create: bool = True,
) -> str | None:
    """按 `(type, normalized)` 精确匹配解析实体，必要时创建。

    Args:
        conn: SQLite 连接对象。
        type: 实体类型。
        name: 原始实体名称；若不是字符串则返回 `None`。
        create: 未命中时是否创建实体，默认为 `True`。

    Returns:
        命中或创建成功时返回 `entity_id`；输入无效、未命中且不创建时返回 `None`。
    """

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
    created_at = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: UP017

    try:
        conn.execute(
            """
            INSERT INTO entities (entity_id, type, name, normalized, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_id, type, name, normalized, created_at),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        row = conn.execute(
            "SELECT entity_id FROM entities WHERE type = ? AND normalized = ?",
            (type, normalized),
        ).fetchone()
        return str(row[0]) if row else None

    return entity_id

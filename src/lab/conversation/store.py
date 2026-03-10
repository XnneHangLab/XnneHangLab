"""Conversation Store — Date-based JSON file persistence.

This module handles reading and appending conversation turns to date-based
JSON files, aligned with Neo4j `conv:YYYY-MM-DD` nodes.

File format::

    conversations/
        2026-03-03.json
        2026-03-04.json
        ...

Each file contains a list of messages::

    [
        {"role": "user", "content": "...", "timestamp": "..."},
        {"role": "assistant", "content": "...", "timestamp": "..."}
    ]

Usage::

    from memory_bench.server.conversation_store import ConversationStore

    store = ConversationStore(base_dir="conversations")

    # Read today's conversation
    messages = store.read_conversation("2026-03-03")

    # Append a new turn
    store.append_turn("2026-03-03", role="user", content="Hello")
    store.append_turn("2026-03-03", role="assistant", content="Hi there!")

    # Start a new file (e.g., "2026-03-03_02.json")
    store.append_turn("2026-03-03_02", role="user", content="New day!")
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

# Avoid importing typing module due to conflict with local typing/ directory
# Use dict instead of dict[str, Any] - works fine with PEP 563


class ConversationStore:
    """Date-based conversation persistence."""

    def __init__(self, base_dir: str = "conversations") -> None:
        """Initialize the conversation store.

        Args:
            base_dir: Directory to store conversation JSON files.
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.log = logger.bind(group="conversation_store")

    def _get_file_path(self, date_id: str) -> Path:
        """Get the file path for a given date ID.

        Args:
            date_id: Date string (e.g., "2026-03-03") or custom ID (e.g., "2026-03-03_02")

        Returns:
            Full file path
        """
        return self.base_dir / f"{date_id}.json"

    def read_conversation(self, date_id: str) -> list[dict[str, str]]:
        """Read conversation messages from a date file.

        Args:
            date_id: Date string (e.g., "2026-03-03") or custom ID

        Returns:
            List of messages, or empty list if file doesn't exist
        """
        file_path = self._get_file_path(date_id)

        if not file_path.exists():
            self.log.info("📄 No conversation file for %s (new conversation)", date_id)
            return []

        try:
            with file_path.open(encoding="utf-8") as f:
                data = json.load(f)
                messages: list[dict[str, str]] = data  # type: ignore[assignment]
                self.log.info("📖 Loaded %d messages from %s", len(messages), date_id)
                return messages
        except json.JSONDecodeError as e:
            self.log.warning("⚠️  Corrupted conversation file %s: %s", date_id, e)
            return []
        except Exception as e:
            self.log.error("❌ Failed to read conversation %s: %s", date_id, e)
            return []

    def append_turn(
        self,
        date_id: str,
        role: str,
        content: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        """Append a new message turn to the conversation file.

        Args:
            date_id: Date string or custom ID
            role: Message role ("user" or "assistant")
            content: Message content
            extra: Optional extra fields (e.g., emotion, metadata)
        """
        file_path = self._get_file_path(date_id)

        # Load existing messages
        messages = self.read_conversation(date_id) if file_path.exists() else []

        # Create new message
        now_iso = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        message: dict[str, str] = {
            "role": role,
            "content": content,
            "timestamp": now_iso,
        }

        # Merge extra fields if provided
        if extra:
            message.update(extra)

        messages.append(message)

        # Write back
        try:
            with file_path.open("w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
            self.log.info("💾 Appended %s turn to %s (total: %d messages)", role, date_id, len(messages))
        except Exception as e:
            self.log.error("❌ Failed to write conversation %s: %s", date_id, e)
            raise

    def list_conversations(self) -> list[str]:
        """List all available conversation date IDs.

        Returns:
            Sorted list of date IDs (e.g., ["2026-03-03", "2026-03-04"])
        """
        if not self.base_dir.exists():
            return []

        files = [f.stem for f in self.base_dir.glob("*.json")]
        return sorted(files)

    def get_today_id(self) -> str:
        """Get today's date ID.

        Returns:
            Date string in YYYY-MM-DD format
        """
        return datetime.now(UTC).strftime("%Y-%m-%d")

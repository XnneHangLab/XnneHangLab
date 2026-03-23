from __future__ import annotations

import re
from dataclasses import dataclass, field

EMOJI_SEQUENCE_RE = re.compile(
    r"(?:"
    r"[\U0001F1E6-\U0001F1FF]{2}"
    r"|"
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF]"
    r"(?:\uFE0F|\uFE0E)?"
    r"(?:\u200D[\U0001F300-\U0001FAFF\u2600-\u27BF](?:\uFE0F|\uFE0E)?)*"
    r")"
)
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
MARKDOWN_HEADER_LINE_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$")
MARKDOWN_THEMATIC_BREAK_RE = re.compile(r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
HTML_BREAK_RE = re.compile(r"(?i)<br\s*/?>")
BROKEN_URL_PROTOCOL_RE = re.compile(r"(?i)\b(https?)\s*:\s*\n\s*//")
SPACE_RE = re.compile(r"[^\S\r\n]+")
NEWLINE_SPACING_RE = re.compile(r"[ \t]*\n[ \t]*")
PARAGRAPH_GAP_RE = re.compile(r"\n{3,}")


@dataclass(slots=True)
class CleanerConfig:
    clean_emoji: bool = True
    emotion_emoji_passthrough: bool = True
    emotion_emoji_set: set[str] | None = field(default=None)
    clean_markdown: bool = True
    normalize_whitespace: bool = True


class TextCleaner:
    def __init__(self, config: CleanerConfig | None = None):
        self.config = config or CleanerConfig()

    def clean(self, text: str) -> str:
        if not text:
            return ""

        cleaned = text

        if self.config.clean_markdown:
            cleaned = MARKDOWN_THEMATIC_BREAK_RE.sub("", cleaned)
            cleaned = HTML_BREAK_RE.sub("\n", cleaned)
            cleaned = MARKDOWN_HEADER_LINE_RE.sub(r"\1", cleaned)
            cleaned = MARKDOWN_BOLD_RE.sub(r"\1", cleaned)
            cleaned = INLINE_CODE_RE.sub(r"\1", cleaned)

        if self.config.clean_emoji:
            cleaned = self._clean_emoji(cleaned)

        if self.config.normalize_whitespace:
            cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
            cleaned = BROKEN_URL_PROTOCOL_RE.sub(r"\1://", cleaned)
            cleaned = SPACE_RE.sub(" ", cleaned)
            cleaned = NEWLINE_SPACING_RE.sub("\n", cleaned)
            cleaned = PARAGRAPH_GAP_RE.sub("\n\n", cleaned)
            cleaned = cleaned.strip()

        return cleaned

    def _clean_emoji(self, text: str) -> str:
        passthrough: set[str] = set()
        if self.config.emotion_emoji_passthrough and self.config.emotion_emoji_set:
            passthrough = set(self.config.emotion_emoji_set)

        def replace(match: re.Match[str]) -> str:
            emoji = match.group(0)
            if emoji in passthrough:
                return emoji
            return ""

        return EMOJI_SEQUENCE_RE.sub(replace, text)

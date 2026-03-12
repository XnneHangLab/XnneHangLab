# type:ignore
# copyright@https://github.com/Open-LLM-VTuber/Open-LLM-VTuber
# 该文件和 Live2d 的代码一样暂时不修改。但其实我应该只会搞英文和日文。后续适配日文的时候才会尝试大修

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, overload

import pysbd
from langdetect import detect
from loguru import logger

from lab.agent.output_types import AudioOutput

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# Constants for additional checks
COMMAS = [
    ",",
    "،",
    "，",
    "、",
    "፣",
    "၊",
    ";",
    "΄",
    "‛",
    "।",
    "﹐",
    "꓾",
    "⹁",
    "︐",
    "﹑",
    "､",
    "،",
]

END_PUNCTUATIONS = [".", "!", "?", "。", "！", "？", "...", "。。。"]
ABBREVIATIONS = [
    "Mr.",
    "Mrs.",
    "Dr.",
    "Prof.",
    "Inc.",
    "Ltd.",
    "Jr.",
    "Sr.",
    "e.g.",
    "i.e.",
    "vs.",
    "St.",
    "Rd.",
    "Dr.",
]
COMMAS = [",", ";", "\u3001", "\uff0c", "\uff1b"]
END_PUNCTUATIONS = [".", "!", "?", "\u3002", "\uff01", "\uff1f", "...", "\u2026\u2026"]
SENTENCE_END_CHARS = {".", "!", "?", "\u3002", "\uff01", "\uff1f"}
TRAILING_SENTENCE_CHARS = set("\"'”’)]}】）」』」")
LIST_MARKER_RE = re.compile(r"(^|[\s\[\(\{\]\)\}])\d+\.$")
FRAGILE_DOT_RE = re.compile(r"(?<!\S)\d+\.(?=\s*\S)|[A-Za-z0-9_/-]+(?:\.[A-Za-z0-9_/-]+)+")

# Set of languages directly supported by pysbd
SUPPORTED_LANGUAGES = {
    "am",
    "ar",
    "bg",
    "da",
    "de",
    "el",
    "en",
    "es",
    "fa",
    "fr",
    "hi",
    "hy",
    "it",
    "ja",
    "kk",
    "mr",
    "my",
    "nl",
    "pl",
    "ru",
    "sk",
    "ur",
    "zh",
}


def detect_language(text: str) -> str:
    """
    Detect text language and check if it's supported by pysbd.
    Returns None for unsupported languages.
    """
    try:
        detected = detect(text)
        return detected if detected in SUPPORTED_LANGUAGES else None
    except Exception as e:
        logger.debug(f"Language detection failed, language not supported by pysdb: {e}")
        return None


def is_complete_sentence(text: str) -> bool:
    """
    Check if text ends with sentence-ending punctuation and not abbreviation.

    Args:
        text: Text to check

    Returns:
        bool: Whether the text is a complete sentence
    """
    text = text.strip()
    if not text:
        return False

    if any(text.endswith(abbrev) for abbrev in ABBREVIATIONS):
        return False

    idx = len(text) - 1
    while idx >= 0 and text[idx] in TRAILING_SENTENCE_CHARS:
        idx -= 1
    if idx < 0:
        return False
    return _boundary_token_length(text, idx) > 0


def contains_comma(text: str) -> bool:
    """
    Check if text contains any comma.

    Args:
        text: Text to check

    Returns:
        bool: Whether the text contains a comma
    """
    return any(comma in text for comma in COMMAS)


def comma_splitter(text: str) -> tuple[str, str]:
    """
    Process text and split it at the first comma.
    Returns the split text (including the comma) and the remaining text.

    Args:
        text: Text to split

    Returns:
        tuple[str, str]: (split text with comma, remaining text)
    """
    if not text:
        return [], ""

    for comma in COMMAS:
        if comma in text:
            split_text = text.split(comma, 1)
            # Return first part with the comma
            return split_text[0].strip() + comma, split_text[1].strip()
    return text, ""


def has_punctuation(text: str) -> bool:
    """
    Check if the text is a punctuation mark.

    Args:
        text: Text to check

    Returns:
        bool: Whether the text is a punctuation mark
    """
    return contains_comma(text) or contains_end_punctuation(text)


def contains_end_punctuation(text: str) -> bool:
    """
    Check if text contains any sentence-ending punctuation.

    Args:
        text: Text to check

    Returns:
        bool: Whether the text contains ending punctuation
    """
    return _find_first_sentence_boundary(text) is not None


def _next_non_space_index(text: str, start: int) -> int | None:
    for idx in range(start, len(text)):
        if not text[idx].isspace():
            return idx
    return None


def _looks_like_abbreviation(text: str, period_idx: int) -> bool:
    probe = text[max(0, period_idx - 12) : period_idx + 1].lower()
    return any(probe.endswith(abbrev.lower()) for abbrev in ABBREVIATIONS)


def _is_inline_period(text: str, idx: int) -> bool:
    if text[idx] != ".":
        return False

    if _looks_like_abbreviation(text, idx):
        return True

    prev_char = text[idx - 1] if idx > 0 else ""
    immediate_next = text[idx + 1] if idx + 1 < len(text) else ""
    next_idx = _next_non_space_index(text, idx + 1)
    next_char = text[next_idx] if next_idx is not None else ""

    # Streaming often pauses on a bare list marker like "1." before the item text arrives.
    if prev_char.isdigit() and next_idx is None:
        return True

    if prev_char.isalnum() and immediate_next.isalnum():
        return True

    number_start = idx
    while number_start > 0 and text[number_start - 1].isdigit():
        number_start -= 1
    marker_candidate = text[max(0, number_start - 1) : idx + 1]
    if LIST_MARKER_RE.fullmatch(marker_candidate):
        return True

    return False


def _boundary_token_length(text: str, idx: int) -> int:
    if idx < 0 or idx >= len(text):
        return 0

    if text.startswith("...", idx):
        return 3
    if text.startswith("\u2026\u2026", idx):
        return 2

    char = text[idx]
    if char not in SENTENCE_END_CHARS:
        return 0
    if char == "." and _is_inline_period(text, idx):
        return 0
    return 1


def _find_first_sentence_boundary(text: str) -> int | None:
    for idx in range(len(text)):
        if _boundary_token_length(text, idx) > 0:
            return idx
    return None


def segment_text_by_rules(text: str) -> tuple[list[str], str]:
    """Segment text with lightweight rules that preserve filenames and list markers."""
    if not text:
        return [], ""

    complete_sentences: list[str] = []
    start = 0
    idx = 0

    while idx < len(text):
        token_len = _boundary_token_length(text, idx)
        if token_len == 0:
            idx += 1
            continue

        end = idx + token_len
        while end < len(text) and text[end] in TRAILING_SENTENCE_CHARS:
            end += 1

        sentence = text[start:end].strip()
        if sentence:
            complete_sentences.append(sentence)

        start = end
        while start < len(text) and text[start].isspace():
            start += 1
        idx = start

    remaining = text[start:].strip()
    return complete_sentences, remaining


def segment_text_by_regex(text: str) -> tuple[list[str], str]:
    """
    Segment text into complete sentences using regex pattern matching.
    More efficient but less accurate than pysbd.

    Args:
        text: Text to segment into sentences

    Returns:
        tuple[list[str], str]: (list of complete sentences, remaining incomplete text)
    """
    return segment_text_by_rules(text)


def segment_text_by_pysbd(text: str) -> tuple[list[str], str]:
    """
    Segment text into complete sentences and remaining text.
    Uses pysbd for supported languages, falls back to regex for others.

    Args:
        text: Text to segment into sentences

    Returns:
        tuple[list[str], str]: (list of complete sentences, remaining incomplete text)
    """
    if not text:
        return [], ""

    if FRAGILE_DOT_RE.search(text):
        return segment_text_by_rules(text)

    try:
        # Detect language
        lang = detect_language(text)

        if lang is not None:
            # Use pysbd for supported languages
            segmenter = pysbd.Segmenter(language=lang, clean=False)
            sentences = segmenter.segment(text)

            if not sentences:
                return [], text

            # Process all but the last sentence
            complete_sentences = []
            for sent in sentences[:-1]:
                sent = sent.strip()
                if sent:
                    complete_sentences.append(sent)

            # Handle the last sentence
            last_sent = sentences[-1].strip()
            if is_complete_sentence(last_sent):
                complete_sentences.append(last_sent)
                remaining = ""
            else:
                remaining = last_sent

        else:
            # Use regex for unsupported languages
            return segment_text_by_regex(text)

        if any(len(sent) <= 2 and contains_end_punctuation(sent) for sent in complete_sentences):
            return segment_text_by_rules(text)

        logger.debug(f"Processed sentences: {complete_sentences}, Remaining: {remaining}")
        return complete_sentences, remaining

    except Exception as e:
        logger.error(f"Error in sentence segmentation: {e}")
        # Fallback to regex on any error
        return segment_text_by_rules(text)


class TagState(Enum):
    """State of a tag in text"""

    START = "start"  # <tag>
    INSIDE = "inside"  # text between tags
    END = "end"  # </tag>
    SELF_CLOSING = "self"  # <tag/>
    NONE = "none"  # no tag


@dataclass
class TagInfo:
    """Information about a tag"""

    name: str
    state: TagState

    def __str__(self) -> str:
        """String representation of tag info"""
        if self.state == TagState.NONE:
            return "none"
        return f"{self.name}:{self.state.value}"


@dataclass
class SentenceWithTags:
    """A sentence with its tag information, supporting nested tags"""

    text: str
    tags: list[TagInfo]  # list of tags from outermost to innermost


class SentenceDivider:
    def __init__(
        self,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
        valid_tags: list[str] = None,
    ):
        """
        Initialize the SentenceDivider.

        Args:
            faster_first_response: Whether to split first sentence at commas
            segment_method: Method for segmenting sentences
            valid_tags: list of valid tag names to detect
        """
        self.faster_first_response = faster_first_response
        self.segment_method = segment_method
        self.valid_tags = valid_tags or ["think"]
        self._is_first_sentence = True
        self._buffer = ""
        # Replace active_tags dict with a stack to handle nesting
        self._tag_stack = []

    def _get_current_tags(self) -> list[TagInfo]:
        """
        Get all current active tags from outermost to innermost.

        Returns:
            list[TagInfo]: list of active tags
        """
        return [TagInfo(tag.name, TagState.INSIDE) for tag in self._tag_stack]

    def _get_current_tag(self) -> TagInfo | None:
        """
        Get the current innermost active tag.

        Returns:
            TagInfo if there's an active tag, None otherwise
        """
        return self._tag_stack[-1] if self._tag_stack else None

    def _extract_tag(self, text: str) -> tuple[TagInfo | None, str]:
        """
        Extract the first tag from text if present.
        Handles nested tags by maintaining a tag stack.

        Args:
            text: Text to check for tags

        Returns:
            tuple of (TagInfo if tag found else None, remaining text)
        """
        # Find the first occurrence of any tag
        first_tag = None
        first_pos = len(text)
        tag_type = None
        matched_tag = None

        # Check for self-closing tags
        for tag in self.valid_tags:
            pattern = f"<{tag}/>"
            match = re.search(pattern, text)
            if match and match.start() < first_pos:
                first_pos = match.start()
                first_tag = match
                tag_type = TagState.SELF_CLOSING
                matched_tag = tag

        # Check for opening tags
        for tag in self.valid_tags:
            pattern = f"<{tag}>"
            match = re.search(pattern, text)
            if match and match.start() < first_pos:
                first_pos = match.start()
                first_tag = match
                tag_type = TagState.START
                matched_tag = tag

        # Check for closing tags
        for tag in self.valid_tags:
            pattern = f"</{tag}>"
            match = re.search(pattern, text)
            if match and match.start() < first_pos:
                first_pos = match.start()
                first_tag = match
                tag_type = TagState.END
                matched_tag = tag

        if not first_tag:
            return None, text

        # Handle the found tag
        if tag_type == TagState.START:
            # Push new tag onto stack
            self._tag_stack.append(TagInfo(matched_tag, TagState.START))
        elif tag_type == TagState.END:
            # Verify matching tags
            if not self._tag_stack or self._tag_stack[-1].name != matched_tag:
                logger.warning(f"Mismatched closing tag: {matched_tag}")
            else:
                self._tag_stack.pop()

        return (TagInfo(matched_tag, tag_type), text[first_tag.end() :].lstrip())

    async def _process_buffer(self) -> list[SentenceWithTags]:
        """
        Process the current buffer and return complete sentences with tags.
        Handles tags that may appear anywhere in the buffer.

        Returns:
            list[SentenceWithTags]: list of sentences with their tag information
        """
        result = []

        while self._buffer.strip():
            # Find the next tag position
            next_tag_pos = len(self._buffer)
            for tag in self.valid_tags:
                patterns = [f"<{tag}>", f"</{tag}>", f"<{tag}/>"]
                for pattern in patterns:
                    pos = self._buffer.find(pattern)
                    if pos != -1 and pos < next_tag_pos:
                        next_tag_pos = pos

            if next_tag_pos == 0:
                # Tag is at the start of buffer
                tag_info, remaining = self._extract_tag(self._buffer)
                if tag_info:
                    result.append(
                        SentenceWithTags(
                            text=self._buffer[: len(self._buffer) - len(remaining)].strip(),
                            tags=[tag_info],  # Tag itself is a single-item list
                        )
                    )
                    self._buffer = remaining
                    continue

            elif next_tag_pos < len(self._buffer):
                # Tag is in the middle - process text before tag first
                text_before_tag = self._buffer[:next_tag_pos]
                current_tags = self._get_current_tags()

                # Preserve text inside active tags as a single chunk.
                if current_tags and text_before_tag.strip():
                    result.append(
                        SentenceWithTags(
                            text=text_before_tag.strip(),
                            tags=current_tags,
                        )
                    )
                # Process complete sentences in plain text before tag
                elif contains_end_punctuation(text_before_tag):
                    sentences, remaining = self._segment_text(text_before_tag)
                    for sentence in sentences:
                        if sentence.strip():
                            result.append(
                                SentenceWithTags(
                                    text=sentence.strip(),
                                    tags=current_tags or [TagInfo("", TagState.NONE)],
                                )
                            )

                    if remaining.strip():
                        result.append(
                            SentenceWithTags(
                                text=remaining.strip(),
                                tags=current_tags or [TagInfo("", TagState.NONE)],
                            )
                        )

                elif text_before_tag.strip():
                    # No complete sentence but has content
                    result.append(
                        SentenceWithTags(
                            text=text_before_tag.strip(),
                            tags=current_tags or [TagInfo("", TagState.NONE)],
                        )
                    )

                # Process the tag
                self._buffer = self._buffer[next_tag_pos:]
                tag_info, remaining = self._extract_tag(self._buffer)
                if tag_info:
                    result.append(
                        SentenceWithTags(
                            text=self._buffer[: len(self._buffer) - len(remaining)].strip(),
                            tags=[tag_info],
                        )
                    )
                    self._buffer = remaining
                continue

            # No tags found - process normal text
            current_tags = self._get_current_tags()

            # Handle first sentence with comma if enabled
            if self._is_first_sentence and self.faster_first_response and contains_comma(self._buffer):
                sentence, remaining = comma_splitter(self._buffer)
                if sentence.strip():
                    result.append(
                        SentenceWithTags(
                            text=sentence.strip(),
                            tags=current_tags or [TagInfo("", TagState.NONE)],
                        )
                    )
                self._buffer = remaining
                self._is_first_sentence = False
                continue

            # Process normal sentences
            if contains_end_punctuation(self._buffer):
                display_sentence = ""
                sentences, remaining = self._segment_text(self._buffer)
                self._is_first_sentence = False
                self._buffer = remaining
                for index, sentence in enumerate(sentences):
                    if sentence.strip():
                        if display_sentence == "":
                            display_sentence = sentence
                        elif len(display_sentence) < 10:
                            display_sentence += sentence
                            if index == len(sentences) - 1:
                                result.append(
                                    SentenceWithTags(
                                        text=display_sentence.strip(),
                                        tags=current_tags or [TagInfo("", TagState.NONE)],
                                    )
                                )
                                break
                            continue
                        result.append(
                            SentenceWithTags(
                                text=display_sentence.strip(),
                                tags=current_tags or [TagInfo("", TagState.NONE)],
                            )
                        )
                        display_sentence = ""
            break

        return result

    @overload
    def process_stream(self, segment_stream: AsyncIterator[str]) -> AsyncIterator[SentenceWithTags]: ...

    @overload
    def process_stream(
        self, segment_stream: AsyncIterator[str | AudioOutput]
    ) -> AsyncIterator[SentenceWithTags | AudioOutput]: ...

    async def process_stream(
        self, segment_stream: AsyncIterator[str | AudioOutput]
    ) -> AsyncIterator[SentenceWithTags | AudioOutput]:
        """
        Process a stream of tokens and yield complete sentences with tag information.
        pysbd may not able to handle ...

        Args:
            segment_stream: An async iterator yielding segments

        Yields:
            SentenceWithTags: Complete sentences with their tag information
        """
        self._full_response = []
        logger.info("Starting sentence processing stream...")
        async for segment in segment_stream:
            if isinstance(segment, AudioOutput):
                yield segment
                continue  # yield 似乎不会像 return 一样终止下面所有的代码。需要手动 continue
            self._buffer += segment
            self._full_response.append(segment)

            # Process buffer after punctuation, when buffer gets too long,
            # or when we see a tag
            should_process = any(
                re.search(f"{tag}(?:/)?>", self._buffer) for tag in self.valid_tags
            ) or has_punctuation(self._buffer)

            if should_process:
                sentences = await self._process_buffer()
                for sentence in sentences:
                    yield sentence

        # Process remaining text at end of stream
        if self._buffer.strip():
            tag_info, remaining = self._extract_tag(self._buffer)
            if tag_info:
                yield SentenceWithTags(
                    text=self._buffer[: len(self._buffer) - len(remaining)].strip(),
                    tags=[tag_info],
                )
                self._buffer = remaining

            if self._buffer.strip():
                sentences, remaining = self._segment_text(self._buffer)
                current_tags = self._get_current_tags()

                for sentence in sentences:
                    if sentence.strip():
                        yield SentenceWithTags(
                            text=sentence.strip(),
                            tags=current_tags or [TagInfo("", TagState.NONE)],
                        )
            if remaining.strip():
                yield SentenceWithTags(
                    text=remaining.strip(),
                    tags=current_tags or [TagInfo("", TagState.NONE)],
                )

    @property
    def complete_response(self) -> str:
        """Get the complete response accumulated so far"""
        return "".join(self._full_response)

    def _segment_text(self, text: str) -> tuple[list[str], str]:
        """Segment text using the configured method"""
        if self.segment_method == "regex":
            return segment_text_by_regex(text)
        return segment_text_by_pysbd(text)

    def reset(self):
        """Reset the divider state for a new conversation"""
        self._is_first_sentence = True
        self._buffer = ""
        self._tag_stack = []

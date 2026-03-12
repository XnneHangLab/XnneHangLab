from __future__ import annotations

import asyncio

from lab.utils.sentence_divider import (
    SentenceDivider,
    contains_end_punctuation,
    segment_text_by_pysbd,
    segment_text_by_regex,
)


def test_regex_splitter_keeps_filename_intact() -> None:
    sentences, remaining = segment_text_by_regex("Read test.txt and report back.")
    assert sentences == ["Read test.txt and report back."]
    assert remaining == ""


def test_regex_splitter_keeps_version_intact() -> None:
    sentences, remaining = segment_text_by_regex("Use v1.2.3 today.")
    assert sentences == ["Use v1.2.3 today."]
    assert remaining == ""


def test_regex_splitter_keeps_numbered_items_together() -> None:
    sentences, remaining = segment_text_by_regex("1. Check file. 2. Read content.")
    assert sentences == ["1. Check file.", "2. Read content."]
    assert remaining == ""


def test_end_punctuation_check_ignores_filename_dot() -> None:
    assert not contains_end_punctuation("test.txt")
    assert contains_end_punctuation("test.txt is present.")


def test_pysbd_path_uses_rule_fallback_for_fragile_dot_patterns() -> None:
    text = "\u8bfb\u53d6 test.txt \u540e\u544a\u8bc9\u6211\u7ed3\u679c\u3002"
    sentences, remaining = segment_text_by_pysbd(text)
    assert sentences == [text]
    assert remaining == ""


def test_sentence_divider_stream_keeps_filename_whole() -> None:
    async def _collect() -> list[str]:
        divider = SentenceDivider(faster_first_response=False, segment_method="pysbd", valid_tags=["think", "tool"])

        async def _source():
            yield "Read test.txt and report back."

        chunks: list[str] = []
        async for chunk in divider.process_stream(_source()):
            chunks.append(chunk.text)
        return chunks

    assert asyncio.run(_collect()) == ["Read test.txt and report back."]

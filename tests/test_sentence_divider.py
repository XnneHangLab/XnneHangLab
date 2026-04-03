from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from lab.utils.sentence_divider import (
    SentenceDivider,
    SentenceWithTags,
    contains_end_punctuation,
    segment_full,
    segment_text_by_pysbd,
    segment_text_by_regex,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class _TestSentenceDivider(SentenceDivider):
    async def process_buffer_for_test(self) -> list[str]:
        return [chunk.text for chunk in await self._process_buffer()]

    def set_buffer_for_test(self, text: str) -> None:
        self._buffer = text

    def append_buffer_for_test(self, text: str) -> None:
        self._buffer += text

    @property
    def buffer_for_test(self) -> str:
        return self._buffer


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


def test_regex_splitter_keeps_emotion_prefixed_number_marker_together() -> None:
    text = "[\u5e73\u9759]1.\u6839\u76ee\u5f55\u91cc\u5df2\u7ecf\u6709 test.txt \u4e86\uff0c\u4e0d\u9700\u8981\u91cd\u65b0\u5efa\u3002"
    sentences, remaining = segment_text_by_regex(text)
    assert sentences == [text]
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
        divider = SentenceDivider(
            faster_first_response=False,
            segment_method="pysbd",
            valid_tags=["think", "tool"],
        )

        async def _source() -> AsyncIterator[str]:
            yield "Read test.txt and report back."

        chunks: list[str] = []
        async for chunk in divider.process_stream(_source()):
            chunks.append(chunk.text)
        return chunks

    assert asyncio.run(_collect()) == ["Read test.txt and report back."]


def test_sentence_divider_stream_keeps_emotion_prefixed_number_marker_together() -> None:
    async def _collect() -> list[str]:
        divider = SentenceDivider(
            faster_first_response=False,
            segment_method="pysbd",
            valid_tags=["think", "tool"],
        )

        async def _source() -> AsyncIterator[str]:
            yield "[\u5e73\u9759]1."
            yield "\u6839\u76ee\u5f55\u91cc\u5df2\u7ecf\u6709 `test.txt` \u4e86\uff0c\u6211\u521a\u624d\u67e5\u8fc7\uff0c\u4e0d\u9700\u8981\u91cd\u65b0\u5efa\u3002"

        chunks: list[str] = []
        async for chunk in divider.process_stream(_source()):
            chunks.append(chunk.text)
        return chunks

    assert asyncio.run(_collect()) == [
        "[\u5e73\u9759]1.\u6839\u76ee\u5f55\u91cc\u5df2\u7ecf\u6709 `test.txt` \u4e86\uff0c\u6211\u521a\u624d\u67e5\u8fc7\uff0c\u4e0d\u9700\u8981\u91cd\u65b0\u5efa\u3002"
    ]


def test_segment_full_keeps_version_intact() -> None:
    sentences = segment_full("Use v1.2.3 today. Ship tomorrow.", segment_method="pysbd")

    assert sentences == ["Use v1.2.3 today.", "Ship tomorrow."]


def test_segment_full_merges_short_interjection_into_following_sentence() -> None:
    sentences = segment_full("[欸。]我刚刚看错了。然后继续。", segment_method="regex")

    assert sentences == ["[欸。]我刚刚看错了。然后继续。"]


def test_segment_full_merges_trailing_short_interjection_backward() -> None:
    sentences = segment_full("我知道了。[欸。]", segment_method="regex")

    assert sentences == ["我知道了。[欸。]"]


def test_segment_full_merges_short_sentence_by_tts_threshold() -> None:
    sentences = segment_full("我懂了。然后继续。", segment_method="regex")

    assert sentences == ["我懂了。然后继续。"]


def test_sentence_divider_stream_waits_for_two_sentences_before_flushing() -> None:
    async def _run() -> tuple[list[str], str]:
        divider = _TestSentenceDivider(
            faster_first_response=False,
            segment_method="regex",
            valid_tags=["think", "tool"],
        )

        divider.set_buffer_for_test("First sentence.")
        first_pass = await divider.process_buffer_for_test()
        assert first_pass == []
        assert divider.buffer_for_test == "First sentence."

        divider.append_buffer_for_test(" Second sentence. Tail fragment")
        second_pass = await divider.process_buffer_for_test()
        return second_pass, divider.buffer_for_test

    chunks, remaining = asyncio.run(_run())
    assert chunks == ["First sentence.", "Second sentence."]
    assert remaining == "Tail fragment"


def test_sentence_divider_stream_flushes_tail_fragment_at_end() -> None:
    async def _collect() -> list[str]:
        divider = SentenceDivider(
            faster_first_response=False,
            segment_method="regex",
            valid_tags=["think", "tool"],
        )

        async def _source() -> AsyncIterator[str]:
            yield "First sentence."
            yield " Second sentence. Tail fragment"

        chunks: list[str] = []
        async for chunk in divider.process_stream(_source()):
            chunks.append(chunk.text)
        return chunks

    assert asyncio.run(_collect()) == ["First sentence.", "Second sentence.", "Tail fragment"]


def test_sentence_divider_stream_merges_short_interjection_before_emitting() -> None:
    async def _collect() -> list[str]:
        divider = SentenceDivider(
            faster_first_response=False,
            segment_method="regex",
            valid_tags=["think", "tool"],
        )

        async def _source() -> AsyncIterator[str]:
            yield "[欸。]"
            yield "我刚刚看错了。然后继续。"

        chunks: list[str] = []
        async for chunk in divider.process_stream(_source()):
            chunks.append(chunk.text)
        return chunks

    assert asyncio.run(_collect()) == ["[欸。]我刚刚看错了。然后继续。"]


def test_sentence_divider_extracts_control_tags_for_first_sentence_only() -> None:
    async def _collect() -> list[SentenceWithTags]:
        divider = SentenceDivider(
            faster_first_response=False,
            segment_method="regex",
            valid_tags=["think", "tool"],
        )

        async def _source() -> AsyncIterator[str]:
            yield "[tts:愉快][expression:脸红] 你好，我先说明一下。接下来继续处理这个问题。"

        chunks: list[SentenceWithTags] = []
        async for chunk in divider.process_stream(_source()):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_collect())
    assert [chunk.text for chunk in chunks] == ["你好，我先说明一下。", "接下来继续处理这个问题。"]
    assert chunks[0].control_tags.tts_emotion_key == "愉快"
    assert chunks[0].control_tags.expression_emotion_key == "脸红"
    assert chunks[1].control_tags.is_empty()


def test_sentence_divider_handles_control_tags_split_across_segments() -> None:
    async def _collect() -> list[SentenceWithTags]:
        divider = SentenceDivider(
            faster_first_response=False,
            segment_method="regex",
            valid_tags=["think", "tool"],
        )

        async def _source() -> AsyncIterator[str]:
            yield "[tts:愉"
            yield "快][expression:脸红] 你好。"

        chunks: list[SentenceWithTags] = []
        async for chunk in divider.process_stream(_source()):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_collect())
    assert len(chunks) == 1
    assert chunks[0].text == "你好。"
    assert chunks[0].control_tags.tts_emotion_key == "愉快"
    assert chunks[0].control_tags.expression_emotion_key == "脸红"

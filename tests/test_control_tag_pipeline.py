from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from lab.agent.output_types import Actions, AudioOutput, SentenceOutput
from lab.agent.transformers import actions_extractor, display_processor, tts_filter
from lab.utils.sentence_divider import ControlTags, SentenceWithTags, TagInfo, TagState

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class _FakeLive2DModel:
    def __init__(self) -> None:
        self.emo_map = {"脸红": 7, "中性": 0}

    def extract_emotion(self, _text: str) -> list[int]:
        return []


def test_actions_extractor_uses_separate_expression_and_tts_control_tags() -> None:
    live2d_model = _FakeLive2DModel()
    sentence = SentenceWithTags(
        text="你好。",
        tags=[TagInfo("", TagState.NONE)],
        control_tags=ControlTags(tts_emotion_key="愉快", expression_emotion_key="脸红"),
    )

    async def _collect() -> Actions:
        @actions_extractor(cast("Any", live2d_model), default_expression_emotion="中性")
        async def _source() -> AsyncIterator[SentenceWithTags]:
            yield sentence

        async for item in _source():
            assert not isinstance(item, AudioOutput)
            _chunk, actions = item
            return actions
        raise AssertionError("expected actions output")

    actions = asyncio.run(_collect())
    assert actions.expressions == [7]
    assert actions.expression_emotion_key == "脸红"
    assert actions.tts_emotion_key == "愉快"
    assert actions.emotion_keys == ["愉快"]


def test_actions_extractor_falls_back_to_default_expression_when_missing() -> None:
    live2d_model = _FakeLive2DModel()
    sentence = SentenceWithTags(
        text="你好。",
        tags=[TagInfo("", TagState.NONE)],
    )

    async def _collect() -> Actions:
        @actions_extractor(cast("Any", live2d_model), default_expression_emotion="中性")
        async def _source() -> AsyncIterator[SentenceWithTags]:
            yield sentence

        async for item in _source():
            assert not isinstance(item, AudioOutput)
            _chunk, actions = item
            return actions
        raise AssertionError("expected actions output")

    actions = asyncio.run(_collect())
    assert actions.expressions == [0]
    assert actions.expression_emotion_key == "中性"
    assert actions.tts_emotion_key is None


def test_display_processor_hides_control_tags_by_default() -> None:
    sentence = SentenceWithTags(
        text="你好。",
        tags=[TagInfo("", TagState.NONE)],
        control_tags=ControlTags(tts_emotion_key="愉快", expression_emotion_key="脸红"),
    )

    async def _collect(show_control_tags: bool) -> str:
        @display_processor(show_control_tags=show_control_tags)
        async def _source() -> AsyncIterator[tuple[SentenceWithTags, Actions]]:
            yield sentence, Actions()

        async for item in _source():
            assert not isinstance(item, AudioOutput)
            _sentence, display, _actions = item
            return display.text
        raise AssertionError("expected display output")

    assert asyncio.run(_collect(show_control_tags=False)) == "你好。"
    assert asyncio.run(_collect(show_control_tags=True)) == "[tts:愉快][expression:脸红] 你好。"


def test_tts_filter_uses_clean_sentence_text_when_debug_tags_are_shown() -> None:
    sentence = SentenceWithTags(
        text="你好。",
        tags=[TagInfo("", TagState.NONE)],
        control_tags=ControlTags(tts_emotion_key="愉快", expression_emotion_key="脸红"),
    )

    async def _collect() -> SentenceOutput:
        @tts_filter()
        @display_processor(show_control_tags=True)
        async def _source() -> AsyncIterator[tuple[SentenceWithTags, Actions]]:
            yield sentence, Actions()

        async for output in _source():
            assert isinstance(output, SentenceOutput)
            return output
        raise AssertionError("expected sentence output")

    output = asyncio.run(_collect())
    assert output.display_text.text == "[tts:愉快][expression:脸红] 你好。"
    assert output.tts_text == "你好。"

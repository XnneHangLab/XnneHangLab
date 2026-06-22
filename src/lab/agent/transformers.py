# type: ignore
from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

from loguru import logger

from lab.agent.output_types import Actions, AudioOutput, DisplayText, SentenceOutput, ToolCallEvent
from lab.config_manager.vtuber import TTSPreprocessorConfig
from lab.utils.sentence_divider import CONTROL_TAG_RE, SentenceDivider, SentenceWithTags, TagState
from lab.utils.tts_preprocessor import tts_filter as filter_text

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from lab.live2d_model import Live2dModel


SILENT_TAGS = {"think", "tool"}
TOOL_MARKER_TEXT = {"<tool>", "</tool>", "<tool/>"}

# Sentinel value sent to the frontend to clear the transient expression layer.
# The frontend detects this value and resets to the base appearance.
NEUTRAL_EXPRESSION_SENTINEL = "__neutral__"


def _resolve_expression_actions(
    chunk: SentenceWithTags,
    live2d_model: Live2dModel | None,
) -> tuple[list[str] | list[int] | None, str | None]:
    if live2d_model is None:
        return None, None

    inv_emo_map = {value: key for key, value in live2d_model.emo_map.items()}
    explicit_key = chunk.control_tags.expression_emotion_key
    if explicit_key is not None:
        resolved_expression = live2d_model.emo_map.get(explicit_key.lower())
        if resolved_expression is not None:
            return [resolved_expression], inv_emo_map.get(resolved_expression, explicit_key)
        # Explicit tag not in emo_map — treat as neutral reset
        logger.debug("Expression tag '{}' not in emo_map, treating as neutral reset.", explicit_key)
        return [NEUTRAL_EXPRESSION_SENTINEL], explicit_key

    legacy_expressions = live2d_model.extract_emotion(chunk.text)
    if legacy_expressions:
        first_expression = legacy_expressions[0]
        return legacy_expressions, inv_emo_map.get(first_expression)

    # No expression tag and no bracket match — send neutral reset
    return [NEUTRAL_EXPRESSION_SENTINEL], None


def sentence_divider(
    faster_first_response: bool = True,
    segment_method: str = "pysbd",
    valid_tags: list[str] = None,
):
    """
    Decorator that transforms token stream into sentences with tags

    Args:
        faster_first_response: bool - Whether to enable faster first response
        segment_method: str - Method for sentence segmentation
        valid_tags: list[str] - list of valid tags to process
    """

    def decorator(
        func: Callable[..., AsyncIterator[str | AudioOutput]],
    ) -> Callable[..., AsyncIterator[SentenceWithTags | AudioOutput]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> AsyncIterator[SentenceWithTags | AudioOutput]:
            divider = SentenceDivider(
                faster_first_response=faster_first_response,
                segment_method=segment_method,
                valid_tags=valid_tags or [],
            )
            # stream = func(*args, **kwargs)
            token_stream = func(*args, **kwargs)
            async for sentence in divider.process_stream(token_stream):
                yield sentence
                logger.debug(f"sentence_divider: {sentence}")

        return wrapper

    return decorator


def actions_extractor(
    live2d_model: Live2dModel | None,
):
    """
    Decorator that extracts actions from sentences
    """

    def decorator(
        func: Callable[..., AsyncIterator[SentenceWithTags | AudioOutput]],
    ) -> Callable[..., AsyncIterator[tuple[SentenceWithTags, Actions] | AudioOutput]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> AsyncIterator[tuple[SentenceWithTags, Actions] | AudioOutput]:
            stream = func(*args, **kwargs)
            async for chunk in stream:
                if isinstance(chunk, (AudioOutput, ToolCallEvent)):
                    yield chunk
                else:
                    actions = Actions()
                    # Internal/status tags should not drive visible emotions.
                    if not any(tag.name in SILENT_TAGS for tag in chunk.tags) and not any(
                        tag.state in [TagState.START, TagState.END] for tag in chunk.tags
                    ):
                        expressions, expression_emotion_key = _resolve_expression_actions(
                            chunk,
                            live2d_model,
                        )
                        if expressions:
                            actions.expressions = expressions
                        actions.expression_emotion_key = expression_emotion_key
                        actions.tts_emotion_key = chunk.control_tags.tts_emotion_key
                        actions.emotion_keys = (
                            [chunk.control_tags.tts_emotion_key] if chunk.control_tags.tts_emotion_key else None
                        )
                    yield chunk, actions

        return wrapper

    return decorator


def display_processor(*, show_control_tags: bool = False):
    """
    Decorator that processes text for display.
    """

    def decorator(
        func: Callable[..., AsyncIterator[tuple[SentenceWithTags, Actions] | AudioOutput]],
    ) -> Callable[..., AsyncIterator[tuple[SentenceWithTags, DisplayText, Actions] | AudioOutput]]:
        @wraps(func)
        async def wrapper(
            *args, **kwargs
        ) -> AsyncIterator[tuple[SentenceWithTags, DisplayText, Actions] | AudioOutput]:
            stream = func(*args, **kwargs)

            async for chunk in stream:
                if isinstance(chunk, (AudioOutput, ToolCallEvent)):
                    yield chunk
                else:
                    sentence, actions = chunk
                    if sentence.text in TOOL_MARKER_TEXT and all(tag.name == "tool" for tag in sentence.tags):
                        continue
                    text = sentence.text
                    if any(tag.name == "tool" and tag.state == TagState.INSIDE for tag in sentence.tags):
                        text = f"{text}\n"
                    # Handle think tag states
                    for tag in sentence.tags:
                        if tag.name == "think":
                            if tag.state == TagState.START:
                                text = "("
                            elif tag.state == TagState.END:
                                text = ")"

                    if show_control_tags:
                        prefix = sentence.control_tags.render_prefix()
                        if prefix:
                            text = f"{prefix} {text}" if text else prefix
                    else:
                        text = CONTROL_TAG_RE.sub("", text).strip()

                    display = DisplayText(text=text)  # Simplified DisplayText creation
                    yield sentence, display, actions

        return wrapper

    return decorator


def tts_filter(
    tts_preprocessor_config: TTSPreprocessorConfig | None = None,
):
    """
    Decorator that filters text for TTS.
    Skips TTS for think tag content.
    """

    def decorator(
        func: Callable[..., AsyncIterator[tuple[SentenceWithTags, DisplayText, Actions] | AudioOutput]],
    ) -> Callable[..., AsyncIterator[SentenceOutput | AudioOutput]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> AsyncIterator[SentenceOutput | AudioOutput]:
            stream = func(*args, **kwargs)
            config = tts_preprocessor_config or TTSPreprocessorConfig()

            # async for sentence, display, actions in sentence_stream:
            async for chunk in stream:
                if isinstance(chunk, (AudioOutput, ToolCallEvent)):
                    yield chunk
                else:
                    sentence, display, actions = chunk
                    if any(tag.name in SILENT_TAGS for tag in sentence.tags):
                        tts = ""
                    else:
                        tts = filter_text(
                            text=sentence.text,
                            remove_special_char=config.remove_special_char,
                            ignore_brackets=config.ignore_brackets,
                            ignore_parentheses=config.ignore_parentheses,
                            ignore_asterisks=config.ignore_asterisks,
                            ignore_angle_brackets=config.ignore_angle_brackets,
                            ignore_urls=config.ignore_urls,
                        )

                    logger.debug(f"[{display.name}] display: {display.text}")
                    logger.debug(f"[{display.name}] tts: {tts}")

                    yield SentenceOutput(
                        display_text=display,
                        tts_text=tts,
                        actions=actions,
                    )

        return wrapper

    return decorator

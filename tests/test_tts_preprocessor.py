from __future__ import annotations

from lab.config_manager.vtuber import TTSPreprocessorConfig
from lab.utils.tts_preprocessor import tts_filter


def test_tts_filter_ignores_urls_but_keeps_surrounding_text() -> None:
    config = TTSPreprocessorConfig(
        remove_special_char=True,
        ignore_brackets=True,
        ignore_parentheses=True,
        ignore_asterisks=True,
        ignore_angle_brackets=True,
        ignore_urls=True,
    )

    assert (
        tts_filter(
            text="请看这个链接 https://example.com/docs 然后继续。",
            remove_special_char=config.remove_special_char,
            ignore_brackets=config.ignore_brackets,
            ignore_parentheses=config.ignore_parentheses,
            ignore_asterisks=config.ignore_asterisks,
            ignore_angle_brackets=config.ignore_angle_brackets,
            ignore_urls=config.ignore_urls,
        )
        == "请看这个链接 然后继续。"
    )


def test_tts_filter_can_return_empty_when_text_is_only_url() -> None:
    config = TTSPreprocessorConfig(
        remove_special_char=True,
        ignore_brackets=True,
        ignore_parentheses=True,
        ignore_asterisks=True,
        ignore_angle_brackets=True,
        ignore_urls=True,
    )

    assert (
        tts_filter(
            text="https://example.com/docs",
            remove_special_char=config.remove_special_char,
            ignore_brackets=config.ignore_brackets,
            ignore_parentheses=config.ignore_parentheses,
            ignore_asterisks=config.ignore_asterisks,
            ignore_angle_brackets=config.ignore_angle_brackets,
            ignore_urls=config.ignore_urls,
        )
        == ""
    )


def test_tts_filter_ignores_line_broken_url() -> None:
    config = TTSPreprocessorConfig(
        remove_special_char=True,
        ignore_brackets=True,
        ignore_parentheses=True,
        ignore_asterisks=True,
        ignore_angle_brackets=True,
        ignore_urls=True,
    )

    assert (
        tts_filter(
            text="see this https:\n//xnnehang.top/posts/default/learn_alma_part1",
            remove_special_char=config.remove_special_char,
            ignore_brackets=config.ignore_brackets,
            ignore_parentheses=config.ignore_parentheses,
            ignore_asterisks=config.ignore_asterisks,
            ignore_angle_brackets=config.ignore_angle_brackets,
            ignore_urls=config.ignore_urls,
        )
        == "see this"
    )

from __future__ import annotations

from lab.utils.text_cleaner import CleanerConfig, TextCleaner


def test_text_cleaner_removes_decorative_emoji() -> None:
    cleaner = TextCleaner()

    assert cleaner.clean("Hello 🙂 world ✨") == "Hello world"


def test_text_cleaner_preserves_whitelisted_emotion_emoji() -> None:
    cleaner = TextCleaner(
        CleanerConfig(
            emotion_emoji_set={"🙂"},
        )
    )

    assert cleaner.clean("Hello 🙂 world ✨") == "Hello 🙂 world"


def test_text_cleaner_strips_basic_markdown() -> None:
    cleaner = TextCleaner()

    assert cleaner.clean("# Title\n**bold** and `code`") == "Title\nbold and code"


def test_text_cleaner_normalizes_whitespace() -> None:
    cleaner = TextCleaner(
        CleanerConfig(
            clean_emoji=False,
            clean_markdown=False,
        )
    )

    assert cleaner.clean("  hello   world \n\n\n next\tline  ") == "hello world\n\nnext line"

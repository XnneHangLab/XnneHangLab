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


def test_text_cleaner_converts_html_breaks_to_paragraph_breaks() -> None:
    cleaner = TextCleaner()

    assert cleaner.clean("first line<br>second line<br/>third line") == "first line\nsecond line\nthird line"


def test_text_cleaner_removes_markdown_thematic_break() -> None:
    cleaner = TextCleaner()

    assert cleaner.clean("第一段。\n---\n第二段。") == "第一段。\n\n第二段。"


def test_text_cleaner_rejoins_line_broken_url_protocol() -> None:
    cleaner = TextCleaner(
        CleanerConfig(
            clean_emoji=False,
            clean_markdown=False,
        )
    )

    assert cleaner.clean("在这里：https:\n//xnnehang.top/posts/default/learn_alma_part1") == (
        "在这里：https://xnnehang.top/posts/default/learn_alma_part1"
    )


def test_text_cleaner_normalizes_whitespace() -> None:
    cleaner = TextCleaner(
        CleanerConfig(
            clean_emoji=False,
            clean_markdown=False,
        )
    )

    assert cleaner.clean("  hello   world \n\n\n next\tline  ") == "hello world\n\nnext line"

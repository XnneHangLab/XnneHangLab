from __future__ import annotations

from lab.utils.sentence_divider import segment_full


def test_segment_full_splits_blog_paragraphs() -> None:
    text = """
# Weekly Notes
This is the first paragraph. It has two sentences.

The second paragraph keeps going without drama. It still ends cleanly.
""".strip()

    assert segment_full(text) == [
        "Weekly Notes",
        "This is the first paragraph.",
        "It has two sentences.",
        "The second paragraph keeps going without drama.",
        "It still ends cleanly.",
    ]


def test_segment_full_splits_novel_paragraphs() -> None:
    text = """
She looked out of the window. Rain tapped the glass.

"We should leave now," he whispered. Nobody moved.
""".strip()

    assert segment_full(text) == [
        "She looked out of the window.",
        "Rain tapped the glass.",
        '"We should leave now," he whispered.',
        "Nobody moved.",
    ]


def test_segment_full_secondary_splits_long_sentence() -> None:
    text = (
        "This sentence is intentionally quite long, with several clauses, and enough commas, "
        "to force a secondary split, while still reading naturally."
    )

    assert segment_full(text, max_sentence_len=40, segment_method="regex") == [
        "This sentence is intentionally quite long,",
        "with several clauses, and enough commas,",
        "to force a secondary split,",
        "while still reading naturally.",
    ]


def test_segment_full_treats_html_break_as_paragraph_boundary() -> None:
    text = "第一段。<br>第二段。<br/>第三段。"

    assert segment_full(text) == [
        "第一段。",
        "第二段。",
        "第三段。",
    ]


def test_segment_full_respects_single_line_break_boundaries() -> None:
    text = """
# 风信，是个好名字
"十年一觉扬州梦，赢得青楼薄幸名。"
""".strip()

    assert segment_full(text) == [
        "风信，是个好名字",
        '"十年一觉扬州梦，赢得青楼薄幸名。"',
    ]


def test_segment_full_keeps_short_sentence_when_merge_would_exceed_max_length() -> None:
    text = "嗯。abcdefghijklmnopqrst."

    assert segment_full(text, max_sentence_len=20, segment_method="regex") == [
        "嗯。",
        "abcdefghijklmnopqrst.",
    ]


def test_segment_full_keeps_line_broken_url_as_one_sentence() -> None:
    text = "在这里：https:\n//xnnehang.top/posts/default/learn_alma_part1\n我们当时试着把 tool model 和 chat model 分离了。"

    assert segment_full(text, max_sentence_len=20, segment_method="regex") == [
        "在这里：https://xnnehang.top/posts/default/learn_alma_part1",
        "我们当时试着把 tool model 和 chat model 分离了。",
    ]

from __future__ import annotations

from lab.utils.sentence_divider import segment_full


def test_segment_full_splits_blog_paragraphs() -> None:
    text = """
# Weekly Notes
This is the first paragraph. It has two sentences.

The second paragraph keeps going without drama. It still ends cleanly.
""".strip()

    assert segment_full(text) == [
        "Weekly Notes This is the first paragraph.",
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

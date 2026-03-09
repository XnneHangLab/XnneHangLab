"""tests/test_asr_combiner.py — asr/combiner.py 的单元测试。"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from lab.asr.combiner import combine_sentences

if TYPE_CHECKING:
    from lab.asr.types import Sentence, Word


def make_sentence(text: str, start: int, end: int, words: list[tuple[str, int, int]] | None = None) -> Sentence:
    """辅助：快速构造 Sentence。words 可选，默认单词等于整句。"""
    if words is None:
        words = [(text, start, end)]
    word_dicts: list[Word] = [cast("Word", {"text": t, "start": s, "end": e}) for t, s, e in words]
    return cast("Sentence", {"text": text, "start": start, "end": end, "Words": word_dicts})


# ── 无合并 ────────────────────────────────────────────────────────────────────


def test_no_combine_when_gap_exceeds_threshold() -> None:
    """句间隔超过 combine_line，保持原样。"""
    s1 = make_sentence("A", 0, 500)
    s2 = make_sentence("B", 1500, 2000)  # gap=1000 > combine_line=400
    result = combine_sentences([s1, s2], combine_line=400, max_sentence_length=100)
    assert len(result) == 2


def test_single_sentence_unchanged() -> None:
    """单句输入结构不变（start/end/Words 正确）。
    注意：combine_sentences 内部用 ' ' + text 拼接，单句也会带前导空格，这是已知行为。
    """
    s = make_sentence("hello", 0, 1000)
    result = combine_sentences([s], combine_line=400, max_sentence_length=100)
    assert len(result) == 1
    assert result[0]["start"] == 0
    assert result[0]["end"] == 1000
    assert "hello" in result[0]["text"]


# ── 基本合并 ──────────────────────────────────────────────────────────────────


def test_two_sentences_merged_when_gap_below_threshold() -> None:
    """句间隔小于 combine_line，两句合并为一句。"""
    s1 = make_sentence("你好", 0, 500)
    s2 = make_sentence("世界", 600, 1000)  # gap=100 < 400
    result = combine_sentences([s1, s2], combine_line=400, max_sentence_length=100)
    assert len(result) == 1
    assert result[0]["start"] == 0
    assert result[0]["end"] == 1000


def test_merged_words_are_concatenated() -> None:
    """合并后 Words 列表应包含两句全部 Words。"""
    s1 = make_sentence("A", 0, 100, [("A", 0, 100)])
    s2 = make_sentence("B", 200, 300, [("B", 200, 300)])
    result = combine_sentences([s1, s2], combine_line=400, max_sentence_length=100)
    assert len(result[0]["Words"]) == 2


# ── 连续合并 ──────────────────────────────────────────────────────────────────


def test_three_consecutive_sentences_merged_into_one() -> None:
    """三句连续间隔都小于 combine_line，应合并为一句。"""
    s1 = make_sentence("A", 0, 100)
    s2 = make_sentence("B", 200, 300)
    s3 = make_sentence("C", 400, 500)
    result = combine_sentences([s1, s2, s3], combine_line=200, max_sentence_length=100)
    assert len(result) == 1
    assert result[0]["start"] == 0
    assert result[0]["end"] == 500


# ── max_sentence_length 截断 ──────────────────────────────────────────────────


def test_max_sentence_length_prevents_merge() -> None:
    """合并后长度超过 max_sentence_length 时不合并。"""
    # 每个 Sentence 包含 3 个 Word，两句共 6 个，超过 max=5
    words = [("X", i * 10, i * 10 + 9) for i in range(3)]
    s1 = make_sentence("XXX", 0, 29, words)
    s2 = make_sentence("YYY", 50, 79, [("Y", 50 + i * 10, 59 + i * 10) for i in range(3)])
    result = combine_sentences([s1, s2], combine_line=400, max_sentence_length=5)
    assert len(result) == 2


def test_max_sentence_length_allows_merge_at_boundary() -> None:
    """合并后长度 == max_sentence_length 时仍允许合并（< 判断）。"""
    words_a = [("A", i * 10, i * 10 + 9) for i in range(2)]
    words_b = [("B", 100 + i * 10, 109 + i * 10) for i in range(2)]
    s1 = make_sentence("AA", 0, 19, words_a)
    s2 = make_sentence("BB", 120, 139, words_b)
    # 合并后共 4 个 Word，max=5 → 4 < 5，应合并
    result = combine_sentences([s1, s2], combine_line=400, max_sentence_length=5)
    assert len(result) == 1


# ── 总句数守恒 ────────────────────────────────────────────────────────────────


def test_total_word_count_preserved_after_combine() -> None:
    """合并前后所有 Sentence 的 Words 总数不变。"""
    sentences = [make_sentence(str(i), i * 100, i * 100 + 50) for i in range(5)]
    result = combine_sentences(sentences, combine_line=200, max_sentence_length=100)
    original_word_count = sum(len(s["Words"]) for s in sentences)
    result_word_count = sum(len(s["Words"]) for s in result)
    assert original_word_count == result_word_count


# ── 边界：gap 恰好等于 combine_line ───────────────────────────────────────────


def test_gap_exactly_equal_to_combine_line_does_not_merge() -> None:
    """gap == combine_line 时不合并（严格小于才合并）。"""
    s1 = make_sentence("A", 0, 100)
    s2 = make_sentence("B", 500, 600)  # gap = 400 == combine_line
    result = combine_sentences([s1, s2], combine_line=400, max_sentence_length=100)
    assert len(result) == 2

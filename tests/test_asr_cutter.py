"""tests/test_asr_cutter.py — asr/cutter.py 的单元测试。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lab.asr.cutter import cut_sentences

if TYPE_CHECKING:
    from lab.asr.types import Sentence


def make_sentence(words: list[tuple[str, int, int]]) -> Sentence:
    """辅助：从 (text, start, end) 三元组列表构造 Sentence。"""
    word_dicts = [{"text": t, "start": s, "end": e} for t, s, e in words]
    return {
        "text": " ".join(t for t, _, _ in words),
        "start": words[0][1],
        "end": words[-1][2],
        "Words": word_dicts,
    }


# ── 无切分点 ──────────────────────────────────────────────────────────────────


def test_no_cut_when_gap_below_threshold() -> None:
    """相邻 Word 间隔小于 cut_line，句子不被切分。"""
    sentence = make_sentence([("你", 0, 500), ("好", 600, 1000)])
    result = cut_sentences([sentence], cut_line=200)
    assert len(result) == 1
    assert result[0]["text"] == "你好"


def test_no_cut_when_single_word() -> None:
    """单词句子永远不切分。"""
    sentence = make_sentence([("hello", 0, 1000)])
    result = cut_sentences([sentence], cut_line=100)
    assert len(result) == 1


# ── 单切分点 ──────────────────────────────────────────────────────────────────


def test_single_cut_point_splits_into_two() -> None:
    """间隔超过 cut_line 时，句子被切成两段。"""
    sentence = make_sentence(
        [
            ("你", 0, 500),
            ("好", 600, 1000),
            ("world", 2000, 3000),  # gap = 1000 > cut_line=500
        ]
    )
    result = cut_sentences([sentence], cut_line=500)
    assert len(result) == 2
    assert result[0]["Words"] == [
        {"text": "你", "start": 0, "end": 500},
        {"text": "好", "start": 600, "end": 1000},
    ]
    assert result[1]["Words"] == [{"text": "world", "start": 2000, "end": 3000}]


def test_cut_preserves_start_end_from_words() -> None:
    """切分后每段的 start/end 必须来自 Words 首尾，不能沿用原句。"""
    sentence = make_sentence(
        [
            ("A", 100, 200),
            ("B", 300, 400),
            ("C", 1500, 1600),  # gap = 1100 > 500
        ]
    )
    result = cut_sentences([sentence], cut_line=500)
    assert result[0]["start"] == 100
    assert result[0]["end"] == 400
    assert result[1]["start"] == 1500
    assert result[1]["end"] == 1600


# ── 多切分点 ──────────────────────────────────────────────────────────────────


def test_multiple_cut_points_split_into_three() -> None:
    """两个切分点产生三段。"""
    sentence = make_sentence(
        [
            ("A", 0, 100),
            ("B", 1200, 1300),  # gap=1100 > 500
            ("C", 2500, 2600),  # gap=1200 > 500
        ]
    )
    result = cut_sentences([sentence], cut_line=500)
    assert len(result) == 3


# ── 多句输入 ──────────────────────────────────────────────────────────────────


def test_multiple_sentences_each_processed_independently() -> None:
    """多句输入时每条句子独立处理，总数正确。"""
    s1 = make_sentence([("你好", 0, 500)])
    s2 = make_sentence(
        [
            ("X", 0, 100),
            ("Y", 1500, 1600),  # gap > 500
        ]
    )
    result = cut_sentences([s1, s2], cut_line=500)
    assert len(result) == 3  # s1 不切，s2 切成 2


# ── 文本重写 ──────────────────────────────────────────────────────────────────


def test_cut_text_is_rewritten_by_words() -> None:
    """切分后文本由 rewrite_sentence_text_by_words 重新组织（中英文空格规则）。"""
    sentence = make_sentence(
        [
            ("你好", 0, 500),
            ("world", 1500, 2000),  # gap > 500
        ]
    )
    result = cut_sentences([sentence], cut_line=500)
    # "你好" 独立成一句，text 应为 "你好"（无多余空格）
    assert result[0]["text"] == "你好"
    assert result[1]["text"] == "world"


# ── 边界：gap 恰好等于 cut_line ───────────────────────────────────────────────


def test_gap_exactly_equal_to_cut_line_does_not_cut() -> None:
    """gap == cut_line 时不切分（严格大于才切）。"""
    sentence = make_sentence(
        [
            ("A", 0, 100),
            ("B", 600, 700),  # gap = 500 == cut_line
        ]
    )
    result = cut_sentences([sentence], cut_line=500)
    assert len(result) == 1

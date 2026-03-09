"""tests/test_srt_helper.py — utils/SrtHelper.py 的单元测试。"""

from __future__ import annotations

import pytest

from lab.utils.SrtHelper import convert_sentence_to_srt, ms_to_srt_time

# ── ms_to_srt_time ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ms, expected",
    [
        (0, "00:00:00,000"),
        (1, "00:00:00,001"),
        (999, "00:00:00,999"),
        (1000, "00:00:01,000"),
        (60_000, "00:01:00,000"),
        (3_600_000, "01:00:00,000"),
        # 1h 2m 3s 456ms
        (3_723_456, "01:02:03,456"),
        # 跨小时边界
        (7_261_001, "02:01:01,001"),
    ],
)
def test_ms_to_srt_time(ms: int, expected: str) -> None:
    assert ms_to_srt_time(ms) == expected


# ── convert_sentence_to_srt ───────────────────────────────────────────────────


def test_convert_sentence_to_srt_basic() -> None:
    sentence = {
        "text": "你好世界",
        "start": 1000,
        "end": 3000,
        "Words": [],
    }
    start_time, end_time, text = convert_sentence_to_srt(sentence)  # type: ignore[arg-type]
    assert start_time == "00:00:01,000"
    assert end_time == "00:00:03,000"
    assert text == "你好世界"


def test_convert_sentence_to_srt_zero_start() -> None:
    sentence = {"text": "hello", "start": 0, "end": 500, "Words": []}
    start_time, end_time, text = convert_sentence_to_srt(sentence)  # type: ignore[arg-type]
    assert start_time == "00:00:00,000"
    assert end_time == "00:00:00,500"
    assert text == "hello"


def test_convert_sentence_to_srt_large_timestamp() -> None:
    """超过一小时的时间戳格式正确。"""
    sentence = {"text": "test", "start": 3_600_000, "end": 3_661_500, "Words": []}
    start_time, end_time, _ = convert_sentence_to_srt(sentence)  # type: ignore[arg-type]
    assert start_time == "01:00:00,000"
    assert end_time == "01:01:01,500"

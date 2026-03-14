from __future__ import annotations

import pytest

from lab.asr.converter import (
    convert_asr_response_to_sentences,
    rewrite_sentence_text_by_words,
)
from lab.asr.whisper.converter import convert_whisper_response_to_sentences


def test_funasr_converter_split_sentence_on_gap_and_rewrite_text() -> None:
    input_data = {
        "key": "demo",
        "text": "你 好 world",
        "timestamp": [[0, 900], [900, 1999], [2700, 3500]],
    }

    sentences = convert_asr_response_to_sentences(input_data)  # type: ignore[arg-type]

    assert len(sentences) == 2

    for sentence in sentences:
        assert sentence["start"] == sentence["Words"][0]["start"]
        assert sentence["end"] == sentence["Words"][-1]["end"]

    assert sentences[0]["text"] == "你好"
    assert sentences[0]["start"] == 0
    assert sentences[0]["end"] == 1999
    assert sentences[0]["Words"] == [
        {"text": "你", "start": 0, "end": 900},
        {"text": "好", "start": 900, "end": 1999},
    ]

    assert sentences[1]["text"] == "world"
    assert sentences[1]["start"] == 2700
    assert sentences[1]["end"] == 3500
    assert sentences[1]["Words"] == [{"text": "world", "start": 2700, "end": 3500}]


def test_funasr_converter_raises_on_mismatched_text_and_timestamps() -> None:
    input_data = {
        "key": "demo",
        "text": "你 好",
        "timestamp": [[0, 1]],
    }

    with pytest.raises(AssertionError):  # type: ignore
        convert_asr_response_to_sentences(input_data)  # type: ignore[arg-type]


def test_rewrite_sentence_text_by_words_spacing_rule() -> None:
    words = [
        {"text": "你", "start": 0, "end": 1},
        {"text": "好", "start": 1, "end": 2},
        {"text": "inspired", "start": 2, "end": 3},
        {"text": "by", "start": 3, "end": 4},
        {"text": "德", "start": 4, "end": 5},
        {"text": "国", "start": 5, "end": 6},
    ]

    assert rewrite_sentence_text_by_words(words) == "你好 inspired by 德国"  # type: ignore[arg-type]


def test_whisper_converter_ms_conversion_and_skip_empty_segment() -> None:
    input_data = {
        "text": "ignored",
        "segments": [
            {
                "id": 0,
                "seek": 0,
                "start": 0.0,
                "end": 1.0,
                "text": "hello world",
                "tokens": [1, 2],
                "temperature": 0.0,
                "avg_logprob": -0.1,
                "compression_ratio": 1.0,
                "no_speech_prob": 0.0,
                "words": [
                    {"word": "hello", "start": 0.0, "end": 0.5, "probability": 0.9},
                    {"word": "world", "start": 0.5, "end": 1.0, "probability": 0.9},
                ],
            },
            {
                "id": 1,
                "seek": 0,
                "start": 1.0,
                "end": 1.5,
                "text": "should be skipped",
                "tokens": [3],
                "temperature": 0.0,
                "avg_logprob": -0.2,
                "compression_ratio": 1.0,
                "no_speech_prob": 0.0,
                "words": [],
            },
        ],
    }

    sentences = convert_whisper_response_to_sentences(input_data)  # type: ignore[arg-type]

    assert len(sentences) == 1
    assert sentences[0]["text"] == "hello world"
    assert sentences[0]["start"] == 0
    assert sentences[0]["end"] == 1000
    assert sentences[0]["Words"][0]["start"] == 0
    assert sentences[0]["Words"][0]["end"] == 500

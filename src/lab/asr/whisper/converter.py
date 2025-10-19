from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab._typing import Sentence, WhisperResponse, Word


def convert_whisper_response_to_sentences(input_data: WhisperResponse) -> list[Sentence]:
    sentences: list[Sentence] = []
    for segment in input_data["segments"]:
        Words: list[Word] = []
        text = segment["text"]
        start = segment["words"][0]["start"]
        end = segment["words"][-1]["end"]
        for word in segment["words"]:
            Words.append(
                {
                    "text": word["word"],
                    "start": int(word["start"] * 1000),
                    "end": int(word["end"] * 1000),
                }
            )
            # 这个 word 不一定是单字，可能是多字，但是共用一个 timestamp
        sentence: Sentence = {
            "text": text,
            "start": int(start * 1000),
            "end": int(end * 1000),
            "Words": Words,
        }
        sentences.append(sentence)
    return sentences

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab.asr.types import ASRResponse, Sentence, Word


def convert_asr_response_to_sentences(input_data: ASRResponse) -> list[Sentence]:
    """将 ASRResponse 转换为句子列表。

    Args:
        input_data: ASR 推理结果，要求 `text` 与 `timestamp` 一一对应。

    Returns:
        list[Sentence]: 依据停顿间隔切分后的句子列表。

    Raises:
        AssertionError: `text` 中的词数与 `timestamp` 数量不一致时抛出。
    """
    words = [word for word in input_data["text"].split(" ") if word]
    timestamps = input_data["timestamp"]
    assert len(words) == len(timestamps), "text 与 timestamps 长度不一致，请检查输入数据。"

    sentences: list[Sentence] = []
    current_words: list[Word] = []

    for index, word in enumerate(words):
        current_words.append(
            {
                "text": word,
                "start": timestamps[index][0],
                "end": timestamps[index][1],
            }
        )

        if index < len(words) - 1:
            gap = timestamps[index + 1][0] - timestamps[index][1]
            if gap > 600:
                sentences.append(
                    {
                        "text": " ".join(item["text"] for item in current_words),
                        "start": current_words[0]["start"],
                        "end": current_words[-1]["end"],
                        "Words": current_words,
                    }
                )
                current_words = []

    if current_words:
        sentences.append(
            {
                "text": " ".join(item["text"] for item in current_words),
                "start": current_words[0]["start"],
                "end": current_words[-1]["end"],
                "Words": current_words,
            }
        )

    for sentence in sentences:
        sentence["text"] = rewrite_sentence_text_by_words(sentence["Words"])

    return sentences


def rewrite_sentence_text_by_words(words: list[Word]) -> str:
    """按中英文混排规则重写句子文本。

    Args:
        words: 句子中的词级时间戳列表。

    Returns:
        str: 去除中文之间空格，并保留英文分词空格后的文本。

    Raises:
        None.
    """
    result = [word["text"] for word in words]
    combined = ""

    for index, current in enumerate(result):
        if index > 0:
            previous = result[index - 1]
            is_current_chinese = all(ord(char) > 127 for char in current)
            is_previous_chinese = all(ord(char) > 127 for char in previous)
            if not is_current_chinese or not is_previous_chinese:
                combined += " "
        combined += current

    return combined.strip()

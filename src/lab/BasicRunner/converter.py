from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab._typing import ASRResponse, Sentence, Word


# =====
# 将 Response 处理成 Sentence 和 Word 的形式，两者都有自己的起始点。
# =====


def convert_asr_response_to_sentences(input_data: ASRResponse) -> list[Sentence]:
    sentences: list[Sentence] = []
    words = input_data["text"].split(" ")
    words = [w for w in words if w]  # 去除空字符串
    timestamps = input_data["timestamp"]
    assert len(words) == len(timestamps), (
        "text 和 timestamps 长度不一致, 请检查输入数据, 重复出现请联系开发者并且提供报错音频"
    )

    curr_sentence_text: list[str] = []
    curr_Words: list[Word] = []

    for i in range(len(words)):
        curr_sentence_text.append(words[i])
        curr_Words.append({"text": words[i], "start": timestamps[i][0], "end": timestamps[i][1]})

        # 判断是否需要切句
        if i < len(words) - 1:
            gap = timestamps[i + 1][0] - timestamps[i][1]
            if gap > 600:
                sentence: Sentence = {
                    "text": " ".join([w["text"] for w in curr_Words]),
                    "start": curr_Words[0]["start"],
                    "end": curr_Words[-1]["end"],
                    "Words": curr_Words,
                }
                sentences.append(sentence)
                curr_sentence_text = []
                curr_Words = []

    # 处理最后一句
    if curr_Words:
        sentence = {
            "text": " ".join([w["text"] for w in curr_Words]),
            "start": curr_Words[0]["start"],
            "end": curr_Words[-1]["end"],
            "Words": curr_Words,
        }
        sentences.append(sentence)

    return sentences


def rewrite_sentence_text_by_words(words: list[Word]) -> str:
    result: list[str] = []
    for word in words:
        result.append(word["text"])
    # 合并文本，中文之间无空格，英文之间有空格，中英文之间有空格
    combined = ""
    for i in range(len(result)):
        current = result[i]
        if i > 0:
            prev = result[i - 1]
            # 判断是否需要加空格
            is_current_chinese = all(ord(char) > 127 for char in current)
            is_prev_chinese = all(ord(char) > 127 for char in prev)
            if not is_current_chinese or not is_prev_chinese:
                combined += " "
        combined += current
    return combined.strip()  # .strip() 是一个字符串方法，用于去除字符串开头和结尾的空白字符（包括空格、换行符 \n、制表符 \t 等）。它不会影响字符串中间的空白字符。

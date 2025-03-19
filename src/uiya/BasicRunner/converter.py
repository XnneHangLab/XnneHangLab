# -*- coding: utf-8 -*-

import re
from uiya.utils.config import load_settings_file
from uiya._typing import AutoModelResponse, Sentence, Word
from uiya._dataclass import RunnerSettings

# =====
# 将 Response 处理成 Sentence 和 Word 的形式，两者都有自己的起始点。
# =====

settings: RunnerSettings = load_settings_file("acgo.toml")


def segment_text(text: str):
    """
    将文本按照标点符号分割成句子列表
    """

    pop_list = settings.basic.punctuation_list

    # 移除 pop_list 中的单引号
    # 应对这种情况, He's a boy. 我希望`He's`被视作一个单词
    pop_list_without_single_quote = pop_list.replace("'", "")

    # 使用负向先行断言和负向后行断言确保单引号左右同时为字母时不分割
    pattern = f"(?<![a-zA-Z])'|'(?![a-zA-Z])|([{pop_list_without_single_quote}])"
    sentences = re.split(pattern, text)
    sentences = [s for s in sentences if s.strip()]  # 去除空白元素
    return sentences


def split_into_words(text: str) -> list[str]:
    """
    将句子分割成单个汉字和单词，保留标点符号
    Example:
    split_into_words("晚安纳尼南尼nony!") -> ['晚', '安', '纳', '尼', '南', '尼', 'nony', '!']
    split_into_words("就的真的妈a等等?") -> ['就', '的', '真', '的', '妈', 'a', '等', '等', '?']
    split_into_words("多喜天dustin birthday.") -> ['多', '喜', '天', 'dustin', 'birthday', '.']
    split_into_words("He's 我见过的。") -> ["He's", '我', '见', '过', '的', '。']
    """

    # 正则表达式用于匹配英文单词、汉字、标点符号和英文缩写
    pattern = re.compile(
        r"[a-zA-Z]+(?:'[a-zA-Z]+)?|[\u4e00-\u9fa5]|[^\u4e00-\u9fa5a-zA-Z\s]"
    )

    # 使用 findall 方法找到所有匹配的部分
    words = pattern.findall(text)

    return words


def match_timestamps_to_words(
    text: str, timestamps: list[list[int]]
) -> list[list[int | str]]:
    """
    将时间戳分配给对应的单词,同时去除标点符号。
    """
    pop_list = settings.basic.punctuation_list
    words: list[str] = split_into_words(text)
    matched: list[list[int | str]] = []
    ts_idx = 0

    for word in words:
        if word in pop_list:
            continue
        start, end = timestamps[ts_idx]
        matched.append([start, end, word])  # 有多少个单词，就匹配多少组 start end.
        ts_idx += 1

    return matched


def calculate_words_length(segmented_text: str) -> int:
    """
    计算分割后单词和汉字的长度
    """
    words = split_into_words(segmented_text)
    length = 0
    for word in words:
        if word not in settings.basic.punctuation_list:
            length += 1
    return length


def convert_response_to_sentences(input_data: AutoModelResponse) -> list[Sentence]:
    pop_list = settings.basic.punctuation_list

    results: list[Sentence] = []
    text = input_data["text"]
    timestamps = input_data["timestamp"]

    sentences = segment_text(text)
    current_ts_idx = 0
    for sentence in sentences:
        if sentence in pop_list:
            continue
        else:
            ts_list = timestamps[current_ts_idx : current_ts_idx + len(sentence)]
            matched = match_timestamps_to_words(sentence, ts_list)
            Words: list[Word] = []
            for start, end, word in matched:
                Word_: Word = {"start": int(start), "end": int(end), "text": str(word)}
                Words.append(Word_)  # type:ignore

            result_item: Sentence = {
                "text": sentence,
                "start": Words[0]["start"],
                "end": Words[-1]["end"],
                "Words": Words,
            }

            results.append(result_item)
            current_ts_idx += calculate_words_length(sentence)

    return results

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lab._dataclass import RunnerSettings
from lab.utils.config import load_settings_file

if TYPE_CHECKING:
    from lab._typing import ASRResponse, Sentence, Word


# =====
# 将 Response 处理成 Sentence 和 Word 的形式，两者都有自己的起始点。
# =====


def segment_text(text: str):
    """
    将文本按照标点符号分割成句子列表
    """
    settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)
    pop_list = settings.punctuation_list

    # 移除 pop_list 中的单引号
    # 应对这种情况, He's a boy. 我希望`He's`被视作一个单词
    pop_list_without_single_quote = pop_list.replace("'", "")

    # 单引号左右同时为字母时不分割
    # TODO 直接把 split_into_words 改造成 seg_text, 不再维护两个逻辑.
    pattern = f"(?<![a-zA-Z])'|'(?![a-zA-Z])|([{pop_list_without_single_quote}])"
    sentences = re.split(pattern, text)
    # for index, s in enumerate(sentences):
    #     # 去除句子两端的空格
    #     if not s:
    #         print("=========")
    #         print(sentences[index-2])
    #         print(sentences[index-1])
    #         print(s)
    #         print(sentences[index+1])
    #         print("=========")
    #         sentences.remove(s)
    # print(len(sentences))
    # word_num = 0
    # for s in sentences:
    # word_num += calculate_words_length(s)
    # print(word_num)
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
    pattern = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?|[\u4e00-\u9fa5]|[^\u4e00-\u9fa5a-zA-Z\s]")

    # 使用 findall 方法找到所有匹配的部分
    words = pattern.findall(text)

    return words


def split_into_words_no_punct(text: str) -> list[str]:
    """
    将输入字符串分割成单词列表。规则如下：
    1. 每个中文字符算作一个独立的“单词”。
    2. 连续的英文字母序列（包括带撇号的缩写，如 "He's", "don't"）算作一个单词。
    3. 忽略所有标点符号和空格。

    示例:
    split_into_words_no_punct("哦，有意思有意思。") -> ['哦', '有', '意', '思', '有', '意', '思']
    split_into_words_no_punct("F特.") -> ['F', '特']
    split_into_words_no_punct("OK来到这儿了。") -> ['OK', '来', '到', '这', '儿', '了']
    split_into_words_no_punct("He's 我见过的。") -> ["He's", '我', '见', '过', '的'] # 正确处理英文缩写
    split_into_words_no_punct("嗯，。") -> ['嗯']
    split_into_words_no_punct("It's a test.") -> ['It's', 'a', 'test']
    split_into_words_no_punct("don't stop") -> ["don't", 'stop']
    """
    # 正则表达式解析:
    # [a-zA-Z]+(?:'[a-zA-Z]+)? : 匹配英文单词，包括那些带有撇号的缩写 (例如 's, 't, 're 等)。
    #    [a-zA-Z]+ : 匹配一个或多个连续的英文字母 (单词的开头或整个单词)。
    #    (?:...) : 非捕获组，用于组合撇号和后面的字母部分。
    #    '[a-zA-Z]+ : 匹配一个撇号跟着一个或多个英文字母。
    #    ? : 表示前面的非捕获组 (撇号和后面的字母) 是可选的。这使得该模式能匹配像 "He" (在 "He's" 中) 或 "word" 这样没有撇号的单词。
    # | : 或运算符，表示匹配左边或右边的模式。
    # [\u4e00-\u9fa5] : 匹配一个中文字符（Unicode 范围 U+4E00 到 U+9FA5）。
    pattern = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?|[\u4e00-\u9fa5]")

    # 使用 findall 方法查找文本中所有匹配正则表达式的部分。
    # findall 会返回一个列表，包含所有不重叠的匹配项。
    # 由于正则表达式只匹配中文或英文单词（含缩写），标点和空格会被自动忽略。
    words = pattern.findall(text)
    return words


def match_timestamps_to_words(text: str, timestamps: list[list[int]]) -> list[list[int | str]]:
    """
    将时间戳分配给对应的单词,同时去除标点符号。
    """
    settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)
    pop_list = settings.punctuation_list
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
    settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)
    words = split_into_words(segmented_text)
    length = 0
    for word in words:
        if word not in settings.punctuation_list:
            length += 1
    return length


def convert_asr_response_to_sentences(input_data: ASRResponse) -> list[Sentence]:
    settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)
    pop_list = settings.punctuation_list

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

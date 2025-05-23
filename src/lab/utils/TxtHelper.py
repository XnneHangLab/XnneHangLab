from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lab._dataclass import RunnerSettings
from lab.utils.config import load_settings_file

if TYPE_CHECKING:
    from pathlib import Path


def split_text_into_sentences_by_punctuation_list(text: str) -> list[str]:
    """
    测试移除文本中的指定标点符号(参见 config)
    """
    settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)
    return re.split(f"([{settings.punctuation_list}])", text)
    # 如果后续碰到 list out of index,可以打印一下看一下文本中出现了什么没有见过的符号然后加入 pop_list。


# 写入行到文件
def write_lines_to_file(file_path: Path, lines: list[str]):
    with file_path.open("w", encoding="utf-8") as file:
        file.writelines(lines)


# 写入长文本到文件,保存时不主动分行。传入什么样，保存时就是什么样。
def write_txt_to_file(file_path: Path, text: str):
    with file_path.open("w", encoding="utf-8") as file:
        file.write(text)
        print(f"已写入文件: {file_path}.")


# 读取文件
def read_file(file_path: Path) -> str:
    with file_path.open(encoding="utf-8") as file:
        return file.read()


# 读取文件并按行返回
def read_file_by_lines(file_path: Path) -> list[str]:
    with file_path.open(encoding="utf-8") as file:
        return file.readlines()


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
    pattern = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?|[\u4e00-\u9fa5]")
    words = pattern.findall(text)
    return words


def split_into_words(text: str) -> list[str]:
    """
    将句子分割成单个汉字和单词，保留标点符号
    Example:
    split_into_words("晚安纳尼南尼nony!") -> ['晚', '安', '纳', '尼', '南', '尼', 'nony', '!']
    split_into_words("就的真的妈a等等?") -> ['就', '的', '真', '的', '妈', 'a', '等', '等', '?']
    split_into_words("多喜天dustin birthday.") -> ['多', '喜', '天', 'dustin', 'birthday', '.']
    split_into_words("He's 我见过的。") -> ["He's", '我', '见', '过', '的', '。']
    """

    pattern = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?|[\u4e00-\u9fa5]|[^\u4e00-\u9fa5a-zA-Z\s]")

    # 使用 findall 方法找到所有匹配的部分
    words = pattern.findall(text)

    return words


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

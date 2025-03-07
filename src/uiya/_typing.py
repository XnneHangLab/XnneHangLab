from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict


# 两条线，一条是直接 mp4 输入。(需要考虑mp4->wav和音视频长度对齐)。
# 一种是音频(wav)直接输入。或者考虑自动转换aac,mp3,m4a->wav.

InputResourceType = Literal["wav", "mp4"]  # m4a,aac,mp3 待定
# 需要同时最小化后缀。


class BasicRunner(TypedDict):
    """Command Status"""

    resource_type: InputResourceType
    input_path: Path
    output_path: Path


class AutoModelResponse(TypedDict):
    """response from funasr models
       Example:
       {'key': 'example',
        'text':'你今天可真是cute呢!'
        'timestamp':[[0, 300], [300,540], [540, 600], [600, 900], [900, 1200], [1200, 1500], [1500, 2200],[2200, 2500]]
     }

    其中，text 单位长度和 timestamp 的长度是相等的。一个中文字符算作一个单位字符，一个完整英文单词算作一个单位字符。
    """

    key: str
    text: str
    timestamp: list[list[int]]


class Sentence(TypedDict):
    """经过加工过的 AutoModelResponse, 只包含一个句子
    Example:
    {
    "text": "你今天可真是cute呢"
    "start": 0,
    "end": 2500,
    "Words": [{'start': 0, 'end': 300, 'text': '你'}, {'start': 300, 'end': 540, 'text': '今'}, {'start': 540, 'end': 600, 'text': '天'}, {'start': 600, 'end': 900, 'text': '可'}, {'start': 900, 'end': 1200, 'text': '真'}, {'start': 1200, 'end': 1500, 'text': '是'}, {'start': 1500, 'end': 2200, 'text': 'cute'}, {'start': 2200, 'end': 2500, 'text': '呢'}]
    }
    注意 Sentence 和 Response 不同是不具有标点符号的，为了方便后续调整句子长度(字幕速度)。
    后续可以用 punc 模型来恢复标点。
    """

    text: str
    start: int  # 句子开始的时间 ,ms
    end: int  # 句子结束的时间
    Words: list[Word]  # 单词列表,包含每个单词开始和结束的时间点。


class Word(TypedDict):
    """Sentence 中的一个字或者英文单词(只是断开的英文字母都视作一个完整单词)
    Args:
        text (str): 单词文本
        start (int): 单词开始的时间,ms
        end (int): 单词结束的时间,ms
    """

    text: str  # 单词
    start: int  # 单词开始的时间
    end: int  # 单词结束的时间


class DebugMessage(TypedDict):
    """debug 用的信息
    Args:
        segmented_text (list[str]): 分割后的文本
        total_words_num (int): 总共统计到的单词数
        total_ts_num (int): 总共统计到的时间戳数
    """

    segmented_text: list[str]
    total_words_num: int
    total_ts_num: int

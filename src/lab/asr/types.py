"""ASR 相关类型定义。"""

from __future__ import annotations

from typing_extensions import TypedDict

# 两条线，一条是直接 mp4 输入。(需要考虑mp4->wav和音视频长度对齐)。
# 一种是音频(wav)直接输入。或者考虑自动转换aac,mp3,m4a->wav.


class ASRResponse(TypedDict):
    """response from character-level asr models
       Example:
    {'key': 'bug_0_30',
    'text': '嗯 嗯  well come to the hollywood reporter actress round',
    'timestamp': [[12590, 12830], [16460, 16700], [27950, 28170], [28170, 28290], [28290, 28390], [28390, 28470], [28470, 28890], [28890, 29290], [29290, 29690], [29690, 30000]]}
    len(text.split(" ")) == len(timestamp), 否则出大问题
    """

    key: str
    text: str
    timestamp: list[list[int]]


class WhisperResponse(TypedDict):
    """
    {'text': '那年长街神一正脑怎么动用',
     'segments': [...], 'language': 'zh'}
    和 Sentence 几乎一致，只不过有一点不同,它的 Word 不一定是单字，可能是多字，但是共用一个 timestamp
    """

    text: str
    segments: list[WhisperSegment]


class WhisperSegment(TypedDict):
    id: int
    seek: int
    start: float
    end: float
    text: str
    tokens: list[int]
    temperature: float
    avg_logprob: float
    compression_ratio: float
    no_speech_prob: float
    words: list[WhisperWord]


class WhisperWord(TypedDict):
    word: str
    start: float
    end: float
    probability: float


class VadResponse(TypedDict):
    """定义 VAD 响应的类型。"""

    key: str  # 音频文件名(不带后缀)
    timestamp: list[list[int]]  # 时间戳列表, 每个元素是一个 [start, end] 的列表
    audio_length: int


class SenseVoiceResponse(TypedDict):
    """response from sensevoice models
      Example:
      {'key': 'example',
       'text': "<|zh|><|NEUTRAL|><|BGM|><|woitn|>那年长街声一正浓策马独游"
       'timestamp':[[8390, 8630], ...]
    }
    key 和 ASRResponse 保持一致,不带后缀的文件名
    text: 带有情感状态标识的语音转换的文本, 不能去掉标点符号
    timestamp: 时间戳, 长度 = Words 的长度 + ！！标点符号的个数！！

    <woitn> 和 <withitn> 代表 without_timestamp 和 with_timestamp
    """

    key: str
    status: str
    text: str
    timestamp: list[list[int]]


class Sentence(TypedDict):
    """经过加工过的 ASRResponse, 只包含一个句子
    Example:
    {
    "text": "你今天可真是cute呢"
    "start": 0,
    "end": 2500,
    "Words": [{'start': 0, 'end': 300, 'text': '你'}, ...]
    }
    注意 Sentence 和 Response 不同是不具有标点符号的，为了方便后续调整句子长度(字幕速度)。
    后续可以用 punc 模型来恢复标点。
    """

    text: str
    start: int  # 句子开始的时间 ,ms
    end: int  # 句子结束的时间
    Words: list[Word]  # 单词列表,包含每个单词开始和结束的时间点。


class Word(TypedDict):
    """Sentence 中的一个字或者英文单词(只是断开的英文字母都视作一个完整单词)"""

    text: str  # 单词
    start: int  # 单词开始的时间,ms
    end: int  # 单词结束的时间,ms


class CutPoint(TypedDict):
    """根据 Sentence 和 Word 的 index 把句子沿着 Word 左侧切开进而调整字幕速度(单句长度)"""

    sentence_index: int
    word_index: int


class DebugMessage(TypedDict):
    """debug 用的信息"""

    segmented_text: list[str]
    total_words_num: int
    total_ts_num: int

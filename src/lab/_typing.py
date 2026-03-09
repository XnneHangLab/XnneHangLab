from __future__ import annotations

from typing import Literal

from typing_extensions import TypedDict

# 两条线，一条是直接 mp4 输入。(需要考虑mp4->wav和音视频长度对齐)。
# 一种是音频(wav)直接输入。或者考虑自动转换aac,mp3,m4a->wav.


class ASRResponse(TypedDict):
    """response from funasr models
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
     'segments': [{'id': 0, 'seek': 0, 'start': 0.0, 'end': 4.48, 'text': '那年长街神一正脑', 'tokens': [50365, 4184, 5157, 32271, 42529, 20432, 2257, 15789, 27067, 239, 50589], 'temperature': 0.0, 'avg_logprob': -0.751380583819221, 'compression_ratio': 0.7659574468085106, 'no_speech_prob': 2.6149443721479315e-11, 'words': [{'word': '那', 'start': 0.0, 'end': 1.12, 'probability': 0.8232907056808472}, {'word': '年', 'start': 1.12, 'end': 1.4, 'probability': 0.9747777581214905}, {'word': '长', 'start': 1.4, 'end': 1.84, 'probability': 0.5218478441238403}, {'word': '街', 'start': 1.84, 'end': 2.28, 'probability': 0.4228086471557617}, {'word': '神', 'start': 2.28, 'end': 2.6, 'probability': 0.1317637413740158}, {'word': '一', 'start': 2.6, 'end': 2.98, 'probability': 0.5581172108650208}, {'word': '正', 'start': 2.98, 'end': 3.68, 'probability': 0.37552937865257263}, {'word': '脑', 'start': 3.68, 'end': 4.48, 'probability': 0.5948238521814346}]},
     {'id': 1, 'seek': 0, 'start': 5.0, 'end': 6.92, 'text': '怎么动用', 'tokens': [50589, 15282, 34961, 9254, 50715], 'temperature': 0.0, 'avg_logprob': -0.751380583819221, 'compression_ratio': 0.7659574468085106, 'no_speech_prob': 2.6149443721479315e-11, 'words': [{'word': '怎么', 'start': 5.0, 'end': 5.84, 'probability': 0.7823060750961304}, {'word': '动', 'start': 5.84, 'end': 6.38, 'probability': 0.42099398374557495}, {'word': '用', 'start': 6.38, 'end': 6.92, 'probability': 0.44825148582458496}]}], 'language': 'zh'}
    """

    # 和 Sentence 几乎一致，只不过有一点不同,它的 Word 不一定是单字，可能是多字，但是共用一个 timestamp
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
    """
    定义 VAD 响应的类型。
    """

    key: str  # 音频文件名(不带后缀)
    timestamp: list[list[int]]  # 时间戳列表, 每个元素是一个 [start, end] 的列表
    audio_length: int


class GPTSoVITSResponse(TypedDict):
    audio_type: Literal["mp3"]
    audio_rate: int
    audio_byte: bytes  # base64.b64encode(opus_bytes).decode("utf-8")


class DeepLXResponse(TypedDict):
    source_text: str  # 源文本
    target_text: str  # 目标文本


class SenseVoiceResponse(TypedDict):
    """response from sensevoice models
      Example:
      {'key': 'example',
       'text': "<|zh|><|NEUTRAL|><|BGM|><|woitn|>那年长街声一正浓策马独游"
       'timestamp':[[8390, 8630], [8670, 8910], [8970, 9210], [9430, 9670], [9850, 10090], [10170, 10410], [10510, 10750], [11330, 11570], [12890, 13130], [13230, 13470], [13590, 13830], [13950, 14635]]
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


class CutPoint(TypedDict):
    """根据 Sentence 和 Word 的 index 把句子沿着 Word 左侧切开进而调整字幕速度(单句长度)
    Args:
         sentence_index: 需要被切的点位于哪个 Sentence
         word_index: 位于该 Sentence 中的哪个 Word
    """

    sentence_index: int
    word_index: int


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


class Packages(TypedDict):
    funasr: bool  # 是否包含 funasr 模块
    to_do_list: bool
    yutto_uiya: bool
    gpt_sovits: bool
    qwen_tts: bool
    memory_bench: bool  # 是否挂载 memory_bench 记忆服务


class AudioSessionStateKeys(TypedDict):
    """audio.py 中用到的 st.session_state 的 key_names"""

    audio_name: str  # 音频文件名(包含后缀), 用来判断是否需要 FileToWav
    audio_file: str  # 音频文件的绝对路径

    # ======= 音频文件获取方式.
    use_upload: str  # 是否使用上传的音频
    use_example: str  # 是否使用示例音频
    use_bilibili: str  # 是否使用 bilibili 模块下载的音频

    # ======= 音频识别
    sentences: str  # 带时间戳的识别结果
    text_result: str  # 不带时间戳的识别结果, only text

    # ======= 界面展示
    preview_srt_file: str  # 实时读取并且预览的 srt 文件 Path

    # ======= 信息提示
    readme: str  # guide
    welcome: str  # welcome
    save: str  # 保存成功后提示信息
    upload: str  # 上传成功后提示信息
    guide: str  # guide

    # ======= 配置文件
    subtitle_speed: str  # 字幕速度
    cut_line: str
    combine_line: str
    max_sentence_length: str  # 最大句子长度
    asr_model_provider: str  # ASR 模型系列 FunASR | Whisper
    whisper_model_size: str  # Whisper 模型规格


class SettingSessionSateKeys(TypedDict):
    """streamlit/setting/set.py 中用到的 st.session_state 的 key_names"""

    batch_size_s: str  # 批处理大小
    device: str  # 设备
    base_model: str  # 基础模型路径
    punc_model: str  # 标点模型路径
    vad_model: str  # VAD 模型路径
    hot_words_path: str  # 热词模型路径
    ffmpeg_path: str  # ffmpeg 路径
    cache_dir: str  # 缓存目录
    custom_output_dir: str  # 是否自定义输出目录
    output_dir: str  # 输出目录
    initial_settings: str  # 初始设置, 用来比对是否有更改
    whisper_models_base_dir: str  # Whisper 模型存放的基础目录
    whisper_model_size: str  # Whisper 模型规格
    asr_model_provider: str  # ASR 模型系列 FunASR | Whisper


class HomeSessionStateKeys(TypedDict):
    """streamlit/project/home.py 中用到的 st.session_state 的 key_names"""

    stars: str  # github stars


class SessionKeys(TypedDict):
    """所有 session_state 的 key_names"""

    short_term_memory: str
    text_response: str

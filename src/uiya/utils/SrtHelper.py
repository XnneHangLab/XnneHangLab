import re
from pathlib import Path

from uiya.utils.TxtHelper import write_txt_to_file
from uiya.utils.config import load_settings_file
from uiya._typing import Sentence


def ms_to_srt_time(ms: int) -> str:
    """将毫秒转换为 SRT 时间格式"""
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    milliseconds = ms % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def convert_sentence_to_srt(sentence: Sentence) -> tuple[str, str, str]:
    """将单个Sentence，处理数据并转换为 SRT 格式"""

    # for index, sentence in enumerate(sentences, start=1):
    start = sentence["start"]
    end = sentence["end"]
    text = sentence["text"]
    start_time = ms_to_srt_time(start)
    end_time = ms_to_srt_time(end)
    return (start_time, end_time, text)


def write_srt_from_sentences(
    sentences: list[Sentence], srt_file_path: Path, remove_punctuation: bool = True
):
    """写入最终的 SRT 文件

    Args:
        Sentences : 经过处理后最终的 Sentences 列表
        srt_file_path (Path): *.srt 文件路径
        remove_punctuation (bool, optional): 是否移除标点符号. Defaults to True.
    """
    settings = load_settings_file("acgo.toml")

    srt_content = ""
    for index, sentence in enumerate(sentences, start=1):
        start_time, end_time, text = convert_sentence_to_srt(sentence)
        srt_content += f"{index}\n{start_time} --> {end_time}\n{text}\n\n"

    if remove_punctuation:
        pattern = rf"{settings.basic.punctuation_list}"
        filtered_content = re.sub(pattern, "", srt_content)
        write_txt_to_file(srt_file_path, filtered_content)
    else:
        write_txt_to_file(srt_file_path, srt_content)

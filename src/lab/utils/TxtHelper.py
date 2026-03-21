from __future__ import annotations

import re
from pathlib import Path

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.utils.console.logger import Logger


def _get_punctuation_list() -> str:
    """读取当前 ASR 配置中的标点符号列表。

    Args:
        None.

    Returns:
        str: `lab.toml` 中配置的标点字符集合。

    Raises:
        None.
    """
    lab_settings: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)
    return lab_settings.asr.punctuation_list


def split_text_into_sentences_by_punctuation_list(text: str) -> list[str]:
    """按配置中的标点列表切分文本。

    Args:
        text: 待切分的原始文本。

    Returns:
        list[str]: 文本片段与标点交替组成的列表。

    Raises:
        None.
    """
    punctuation_list = _get_punctuation_list()
    return re.split(f"([{punctuation_list}])", text)


def write_lines_to_file(file_path: Path, lines: list[str]) -> None:
    """将多行文本写入文件。

    Args:
        file_path: 目标文件路径。
        lines: 待写入的多行文本。

    Returns:
        None.

    Raises:
        OSError: 文件写入失败时抛出。
    """
    with file_path.open("w", encoding="utf-8") as file:
        file.writelines(lines)


def write_txt_to_file(file_path: Path, text: str) -> None:
    """将完整文本写入文件。

    Args:
        file_path: 目标文件路径。
        text: 待写入的文本内容。

    Returns:
        None.

    Raises:
        OSError: 文件写入失败时抛出。
    """
    with file_path.open("w", encoding="utf-8") as file:
        file.write(text)
        Logger.info(f"已写入文件 {file_path}.")


def read_file(file_path: Path) -> str:
    """读取整个文本文件。

    Args:
        file_path: 待读取的文件路径。

    Returns:
        str: 文件全部内容。

    Raises:
        OSError: 文件读取失败时抛出。
    """
    with file_path.open(encoding="utf-8") as file:
        return file.read()


def read_file_by_lines(file_path: Path) -> list[str]:
    """按行读取文本文件。

    Args:
        file_path: 待读取的文件路径。

    Returns:
        list[str]: 文件的逐行内容。

    Raises:
        OSError: 文件读取失败时抛出。
    """
    with file_path.open(encoding="utf-8") as file:
        return file.readlines()


def split_into_words_no_punct(text: str) -> list[str]:
    """将文本切分为中英文字词并忽略标点。

    Args:
        text: 待分词的原始文本。

    Returns:
        list[str]: 去除标点后的字词列表。

    Raises:
        None.
    """
    pattern = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?|[\u4e00-\u9fa5]")
    return pattern.findall(text)


def split_into_words(text: str) -> list[str]:
    """将文本切分为中英文字词并保留标点。

    Args:
        text: 待分词的原始文本。

    Returns:
        list[str]: 包含中英文字词与标点的列表。

    Raises:
        None.
    """
    pattern = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?|[\u4e00-\u9fa5]|[^\u4e00-\u9fa5a-zA-Z\s]")
    return pattern.findall(text)


def calculate_words_length(segmented_text: str) -> int:
    """计算文本中非标点字词的数量。

    Args:
        segmented_text: 待统计的文本。

    Returns:
        int: 去除标点后的字词数量。

    Raises:
        None.
    """
    punctuation_list = _get_punctuation_list()
    length = 0
    for word in split_into_words(segmented_text):
        if word not in punctuation_list:
            length += 1
    return length


def read_prompt_from_text_file(prompt_path: str) -> str:
    """读取提示词文件内容。

    Args:
        prompt_path: 提示词文件路径。

    Returns:
        str: 文件中的完整提示词文本。

    Raises:
        ValueError: 文件不存在时抛出。
    """
    prompt_text_path = Path(prompt_path)
    if not prompt_text_path.exists():
        raise ValueError(f"prompt file {prompt_text_path} not exists")
    with prompt_text_path.open("r", encoding="utf-8") as file:
        return file.read()

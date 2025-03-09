import re

from pathlib import Path

from uiya._dataclass import ConfigParser


def split_text_into_sentences_by_punctuation_list(text: str) -> list[str]:
    """
    测试移除文本中的指定标点符号(参见 config)
    """
    Config = ConfigParser()
    return re.split(f"([{Config.punctuation_list}])", text)
    # 如果后续碰到 list out of index,可以打印一下看一下文本中出现了什么没有见过的符号然后加入 pop_list。


# 写入行到文件
def write_lines_to_file(file_path: Path, lines: list[str]):
    with open(file_path, "w", encoding="utf-8") as file:
        file.writelines(lines)


# 写入长文本到文件,保存时不主动分行。传入什么样，保存时就是什么样。
def write_txt_to_file(file_path: Path, text: str):
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(text)


# 读取文件
def read_file(file_path: Path) -> str:
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


# 读取文件并按行返回
def read_file_by_lines(file_path: Path) -> list[str]:
    with open(file_path, "r", encoding="utf-8") as file:
        return file.readlines()

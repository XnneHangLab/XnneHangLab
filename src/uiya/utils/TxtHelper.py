from pathlib import Path


# 写入行到文件
def write_lines_to_file(file_path: Path, lines: list[str]):
    with open(file_path, "w", encoding="utf-8") as file:
        file.writelines(lines)


# 写入长文本到文件,保存时不主动分行。传入什么样，保存时就是什么样。
def write_long_txt_to_file(file_path: Path, txt: str):
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(txt)

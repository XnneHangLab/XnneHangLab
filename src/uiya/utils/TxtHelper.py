from pathlib import Path

from uiya._typing import AutoModelResponse


def save_only_text_from_response(response: AutoModelResponse, output_dir: Path):
    """将文本单独保存到txt文件中 --only-text
    Args:
        response (AutoModelResponse): AutoModel 返回的参数。参见 _typing.py
        input_path (Path): 输入的音频或者视频文件.
        output_dir (Path): 输到哪个的文件夹
    """
    # TODO: 优化这些 print 为 Logger
    print("开始单独保存文本")
    save_path = output_dir / (response["key"] + ".txt")
    with open(save_path, "w", encoding="utf-8") as file:
        file.write(response["text"])


# 写入行到文件
def write_lines_to_file(file_path: Path, lines: list[str]):
    with open(file_path, "w", encoding="utf-8") as file:
        file.writelines(lines)

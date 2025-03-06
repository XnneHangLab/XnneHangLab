from pathlib import Path

from uiya._typing import AutoModelResponse


# 从 AutoModelResponse 中解析无 time stamp 的 text
def save_only_text_from_response(response: AutoModelResponse, output_dir: Path):
    """将文本单独保存到txt文件中 --only-text
    Args:
        response (AutoModelResponse): AutoModel 返回的参数。参见 _typing.py
        input_path (Path): 输入的音频或者视频文件.
        output_dir (Path): 输到哪个的文件夹
    """
    # TODO: 优化这些 print 为 Logger
    print("开始单独保存文本")
    if output_dir.exists() is False:
        output_dir.mkdir(parents=True)
    save_path = output_dir / (response["key"] + "_only_text.txt")
    with open(save_path, "w", encoding="utf-8") as file:
        file.write(response["text"])

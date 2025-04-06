from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from lab._typing import ASRResponse

# =======
# 直接从 ASRResponse 或者 Sentence (经过 converter 加工过的 ASRResponse )中解析出想要的信息并且保存。
# =======


# 从 ASRResponse 中解析无 time stamp 的 text
def save_only_text_from_response(response: ASRResponse, output_dir: Path) -> str:
    """将文本单独保存到txt文件中 --only-text
    Args:
        response (ASRResponse): AutoModel 返回的参数。参见 _typing.py
        input_path (Path): 输入的音频或者视频文件.
        output_dir (Path): 输到哪个的文件夹
    """
    # TODO: 优化这些 print 为 Logger
    print("开始单独保存文本")
    if output_dir.exists() is False:
        output_dir.mkdir(parents=True)
    save_path = output_dir / (response["key"] + "_only_text.txt")
    with save_path.open("w", encoding="utf-8") as file:
        file.write(response["text"])

    return response["text"]


def save_response_from_sensevoice_response() -> None:
    pass

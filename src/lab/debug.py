from __future__ import annotations

import sys
from pathlib import Path

# from lab.funasr.converter import split_into_words
from lab.__main__ import main as basic_runner
from lab.utils.console.logger import Logger
from lab.utils.FFmpegHelper import file_to_opus, split_opus_audio

# 排查音频中存在的异常点的具体位置.
# 思路: 切片, 循环检查(rec_asr_response, 对比 time_stamp 和 len(split_into_words)) 的具体大小, 如果不一样大, 那么说明该位置存在异常点, 然后再对该位置更细致地排查和修复.
# 原则: 尽量让代码健壮, 更具备泛化性


def split_audio_and_detect(input_path: Path, output_dir: Path, seg_length: int = 30, start_time: int = 0):
    opus_file = Path("bug.opus")  # 直接生成在当前目录下
    if opus_file.exists():
        Logger.info("已存在 bug.opus, 直接使用, 如果要开始新的 debug ,请先删除 bug.opus")
    else:
        file_to_opus(input_path=input_path, output_path=opus_file)

    output_path = split_opus_audio(  # 仅支持 opus
        input_path=opus_file, output_dir=output_dir, seg_length=seg_length, start_time=start_time
    )
    # 模拟命令行参数
    sys.argv = [
        "",  # 必要的占位 solving error: unrecognized arguments:
        "--input_path",
        str(output_path),  # 输入音频文件路径
    ]

    # 调用 basic_runner (即 main 函数)
    basic_runner()  # type: ignore
    return output_path


def main():
    input_path = Path("downloads/SpiritFarer/sheding/设定集1-购买部分.mp4")  # 输入音频文件路径
    output_dir = Path("debug")
    seg_length = 40  # 每个切片的长度（秒）
    start_time = 400  # 开始时间（秒）

    split_audio_and_detect(input_path, output_dir, seg_length, start_time)


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys
from pathlib import Path

# from lab.BasicRunner.converter import split_into_words
from lab.cli import main as basic_runner
from lab.utils.FFmpegHelper import split_opus_audio

# 排查音频中存在的异常点的具体位置.
# 思路: 切片, 循环检查(rec_asr_response, 对比 time_stamp 和 len(split_into_words)) 的具体大小, 如果不一样大, 那么说明该位置存在异常点, 然后再对该位置更细致地排查和修复.
# 原则: 尽量让代码健壮, 更具备泛化性


def split_audio_and_detect(input_path: Path, output_dir: Path, seg_length: int = 30, start_time: int = 0):
    output_path = split_opus_audio(
        input_path=input_path, output_dir=output_dir, seg_length=seg_length, start_time=start_time
    )
    # 构造 sys.argv，模拟命令行参数
    sys.argv = [
        "",  # sys.argv[0] 通常是脚本名称，这里用空字符串占位
        "--input_path",
        str(output_path),  # 输入音频文件路径
        "--return-asr-response",
    ]

    # 调用 basic_runner (即 main 函数)
    response = basic_runner()  # type: ignore
    print(response)


def main():
    input_path = Path("bug.opus")
    output_dir = Path("debug")
    seg_length = 30  # 每个切片的长度（秒）
    start_time = 0  # 开始时间（秒）

    split_audio_and_detect(input_path, output_dir, seg_length, start_time)


if __name__ == "__main__":
    main()

from pathlib import Path
from uiya.utils.config import load_settings_file
from uiya.utils.SubprocessHelper import run_shell_command
from uiya._dataclass import RunnerSettings


settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)
FFMPEG_PATH = settings.FFMPEG_PATH


def test_call_ffmpeg():
    command = ["ffmpeg", "-version"]
    result = run_shell_command(command=command)

    if result.returncode == 0:
        print("ffmpeg is accessible")
        return True
    else:
        print("ffmpeg is not asscessible")
        return False


def mp4_to_wav(input_mp4_path: Path, output_wav_path: Path):
    """
    使用 ffmpeg 将 MP4 文件转换为 WAV 文件，并应用指定的参数，使用 run_shell_command 执行命令。
    """
    command = [
        str(FFMPEG_PATH),
        "-y",  # 强制覆盖输出文件
        "-i",
        str(input_mp4_path.absolute()),
        "-vn",  # 禁用视频流
        "-af",
        "aresample=async=1",  # 音频滤波器，异步重采样
        "-acodec",
        "pcm_s16le",  # 音频编码器，PCM s16le (16-bit signed little-endian)
        "-ar",
        "44100",  # 音频采样率，44100 Hz
        "-ac",
        "2",  # 音频通道数，2 (立体声)
        str(output_wav_path.absolute()),
    ]

    result = run_shell_command(command)  # 使用 run_shell_command 执行命令

    if result.returncode == 0:
        print(f"MP4 文件 '{input_mp4_path}' 成功转换为 WAV 文件 '{output_wav_path}'")
        return True
    else:
        print(f"FFmpeg 转换失败，返回码: {result.returncode}")
        # run_shell_command 已经记录了错误信息，这里可以不再重复打印 stderr/stdout
        return False

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from lab.config_manager import FunASRSettings, load_settings_file
from lab.utils.console.logger import Logger
from lab.utils.SubprocessHelper import run_shell_command

if TYPE_CHECKING:
    from pathlib import Path


def test_call_ffmpeg():
    settings: FunASRSettings = load_settings_file("funasr.toml", FunASRSettings)
    FFMPEG_PATH = settings.FFMPEG_PATH
    command = [FFMPEG_PATH, "-version"]
    result = run_shell_command(command=command)

    if result.returncode == 0:
        print("ffmpeg is accessible")
        return True
    else:
        print("ffmpeg is not asscessible")
        return False


def file_to_wav(input_path: Path, output_wav_path: Path):
    """
    使用 ffmpeg 将 * 文件转换为 WAV 文件，并应用指定的参数，使用 run_shell_command 执行命令。
    可以处理 MP4, MP3, AAC, FLAC, etc. 等 FFmpeg 支持的格式。
    """

    settings: FunASRSettings = load_settings_file("funasr.toml", FunASRSettings)
    FFMPEG_PATH = settings.FFMPEG_PATH
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    if input_path.suffix.lower() == ".wav":
        print("\033[1;34m🎧 文件已经是 WAV 格式，无需转换。\033[0m")
        return input_path

    command = [
        str(FFMPEG_PATH),
        "-y",  # 强制覆盖输出文件
        "-i",
        str(input_path.absolute()),
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
        print(f"\033[1;34m🎧 '{input_path}' 成功转换为 WAV 文件 '{output_wav_path}'")
        return True
    else:
        print(f"FFmpeg 转换失败，返回码: {result.returncode}")
        # run_shell_command 已经记录了错误信息，这里可以不再重复打印 stderr/stdout
        return False


def file_to_mp3(input_path: Path, output_path: Path):
    settings: FunASRSettings = load_settings_file("funasr.toml", FunASRSettings)
    FFMPEG_PATH = settings.FFMPEG_PATH
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    if input_path.suffix.lower() == ".mp3":
        print("\033[1;34m🎧 文件已经是 MP3 格式，无需转换。\033[0m")
        return input_path

    command = [
        str(FFMPEG_PATH),
        "-i",
        str(input_path),
        "-vn",
        "-y",
        "-acodec",
        "libmp3lame",
        "-ab",
        "320k",
        "-f",
        "mp3",
        str(output_path),
    ]

    result = run_shell_command(command)

    if result.returncode == 0:
        print(f"🎧 文件 '{input_path}' 成功转换为 MP3 文件 '{output_path}'")
        return output_path
    else:
        print(f"FFmpeg 转换失败，返回码: {result.returncode}")
        return None


def file_to_opus(input_path: Path, output_path: Path):
    """
    使用 ffmpeg 将 * 文件转换为 Opus 文件，并应用指定的参数，使用 run_shell_command 执行命令。
    可以处理 MP4, MP3, AAC, FLAC, etc. 等 FFmpeg 支持的格式。
    """
    # TODO 这一步可能比较久,但是只在结束时输出, 可以考虑用 wepxct 和 pexpect
    settings: FunASRSettings = load_settings_file("funasr.toml", FunASRSettings)
    FFMPEG_PATH = settings.FFMPEG_PATH
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    if input_path.suffix.lower() == ".opus":
        Logger.info("文件已经是 Opus 格式，无需转换。")
        return input_path

    command = [
        str(FFMPEG_PATH),
        "-y",
        "-i",
        str(input_path.absolute()),
        "-vn",
        "-c:a",
        "libopus",
        "-f",
        "ogg",  # 使用ogg容器格式（标准opus封装）
        "-ar",
        "48000",  # Opus推荐使用48000Hz
        "-b:a",
        "64k",  # 推荐64k比特率
        "-vbr",  # 添加可变比特率参数
        "on",  # 开启VBR模式
        "-application",  # 指定编码应用场景
        "voip",  # 针对语音优化（可选值：voip/audio/restricted_lowdelay）
        str(output_path),  # 修改输出扩展名为ogg
    ]

    result = run_shell_command(command)  # 使用 run_shell_command 执行命令

    if result.returncode == 0:
        Logger.info(f"'{input_path}' 成功转换为 Opus 文件 '{output_path}'")
        return True
    else:
        print(f"FFmpeg 转换失败，返回码: {result.returncode}")
        # run_shell_command 已经记录了错误信息，这里可以不再重复打印 stderr/stdout
        return False


# ffmpeg -i 输入文件名 -vn -c:a libopus 输出文件名.opus  # 仅提取音频为 opus
def split_opus_audio(input_path: Path, output_dir: Path, start_time: int, seg_length: int) -> Path:
    # 仅支持 opus
    settings: FunASRSettings = load_settings_file("funasr.toml", FunASRSettings)
    FFMPEG_PATH = settings.FFMPEG_PATH
    # 确保输出目录存在
    if output_dir.exists():
        # 删除目录以及其中的所有文件
        shutil.rmtree(str(output_dir))  # Path.rmdir 无法删除目录不为空的情况

    output_dir.mkdir(parents=True, exist_ok=True)

    end_time = start_time + seg_length
    # 构造输出文件名，自增编号
    output_filename = f"{input_path.stem}_{start_time}_{end_time}.opus"
    output_path = output_dir / output_filename

    # 构建 ffmpeg 命令
    cmd = [
        FFMPEG_PATH,
        "-i",
        str(input_path),  # 输入文件
        "-ss",
        str(start_time),  # 起始时间（秒）
        "-t",
        str(seg_length),  # 切片时长（秒）
        "-c",
        "copy",  # 直接复制，不重新编码
        "-y",  # 覆盖输出文件（如果存在）
        str(output_path),  # 输出文件路径
    ]

    # 执行 ffmpeg 命令
    run_shell_command(command=cmd)
    return output_path


def get_audio_duration(input_path: Path) -> int:
    """
    使用 FFmpeg 获取音频文件的时长（以毫秒为单位）。

    支持音频格式:
        MP3
        WAV
        FLAC
        AAC
        OGG
        M4A
        WMA
        AIFF

    返回:
        时长（毫秒），如果读取失败则返回 0。
    """
    # 调用 ffprobe 获取时长
    cmd = [
        "ffprobe",  # 不对外开放, 不提供配置项
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    result = run_shell_command(command=cmd)
    duration_seconds = float(result.stdout.strip())
    duration_ms = int(duration_seconds * 1000)
    return duration_ms

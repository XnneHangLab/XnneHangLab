from __future__ import annotations

import argparse
from pathlib import Path

from lab.__version__ import VERSION
from lab.config_manager import FunASRSettings, XnneHangLabSettings, load_settings_file
from lab.utils.console.logger import Badge, Logger


def path_from_cli(path: str) -> Path:
    """从命令行参数获取路径，支持 ~，以便配置中使用 ~"""
    return Path(path).expanduser()


SUBCOMMANDS = ["recognize", "punc_recover", "vad"]


def handle_default_subcommand(argv: list[str]) -> list[str]:
    if len(argv) == 0:
        return ["recognize", *argv]
    if argv[0] not in SUBCOMMANDS and argv[0] not in ["-v", "--version"]:
        argv.insert(0, "recognize")

    return argv


def show_args(args: argparse.Namespace):
    for key, value in vars(args).items():
        Logger.custom(value, Badge(key, fore="green"))


# 定义长文本写入函数
def cli():
    # rec mode  input_file (wav,opus..)-> asr_full_response , asr_vad_response   --     # subtitle_mode input_file(wav,opus..)->(srt , att)
    # punc_recover_mode input_text (str)  -> punc_response

    parser = argparse.ArgumentParser(description="音频转文字工具ya~")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {VERSION}", help="显示版本号")
    settings: XnneHangLabSettings = load_settings_file("lab.toml", XnneHangLabSettings)

    subparsers = parser.add_subparsers(dest="command", help="支持的子命令")
    rec_parser = subparsers.add_parser("recognize", help="识别音频文件")
    punc_recover_parser = subparsers.add_parser("punc_recover", help="标点恢复")
    vad_parser = subparsers.add_parser("vad", help="VAD 语音活动检测")

    add_recognize_arguments(rec_parser, settings.funasr)
    add_punc_recover_arguments(punc_recover_parser, settings.funasr)
    add_vad_arguments(vad_parser, settings.funasr)
    return parser


def add_recognize_arguments(parser: argparse.ArgumentParser, settings: FunASRSettings):
    # basic-setting
    group_config = parser.add_argument_group("setting", "配置项")
    group_config.add_argument(
        "--batch_size_s", type=int, default=settings.batch_size_s, help=f"批处理大小, 默认为 {settings.batch_size_s}"
    )
    group_config.add_argument(
        "--device", type=str, default=settings.device, help=f"计算设备(cpu/gpu), 默认为 {settings.device}"
    )
    group_config.add_argument(
        "--output-dir", type=path_from_cli, default=path_from_cli(settings.output_dir), help="输出目录"
    )
    group_config.add_argument(
        "--cache_dir", type=path_from_cli, default=path_from_cli(settings.cache_dir), help="缓存目录"
    )
    group_config.add_argument("--hotwords", type=str, default=settings.hot_words_path, help="热词或者热词(txt)的路径")
    group_config.add_argument("--ffmpeg-path", type=str, default=settings.FFMPEG_PATH, help="ffmpeg的路径")
    group_config.add_argument(
        "--base-model", type=path_from_cli, default=path_from_cli(settings.base_model), help="基础模型的路径"
    )
    group_config.add_argument(
        "--punc-model", type=path_from_cli, default=path_from_cli(settings.punc_model), help="分词模型的路径"
    )
    group_config.add_argument(
        "--vad-model", type=path_from_cli, default=path_from_cli(settings.vad_model), help="VAD模型的路径"
    )
    group_config.add_argument("--cut", action="store_true", help="是否裁剪长句, 不可以和合并短句同时使用")
    group_config.add_argument("--combine", action="store_true", help="是否合并短句, 不可以和裁剪长句同时使用")
    group_config.add_argument(
        "--combine-line",
        type=int,
        default=settings.combine_line,
        help=f"合并短句的间隔临界值(ms), 默认为 {settings.combine_line} ",
    )
    group_config.add_argument(
        "--cut-line", type=int, default=settings.cut_line, help=f"裁剪长句的间隔临界值(ms), 默认为 {settings.cut_line} "
    )
    group_config.add_argument(
        "--max-sentence-length",
        type=int,
        default=settings.max_sentence_length,
        help=f"最大句子长度,默认为 {settings.max_sentence_length} , 当句子超过这个长度时,就不再合并了",
    )
    group_config.add_argument("--need-punc", action="store_true", help="是否需要标点符号")
    # 隐藏了 punc_list , custom_output_dir, 前者除非出现新的未知标点符号导致 list index out of range 否则不需要修改, 后者只是用于维持 WebUI 的状态的.

    group_basic = parser.add_argument_group("basic", "基础参数")
    group_basic.add_argument(
        "-i",
        "--input_path",
        type=path_from_cli,
        default=path_from_cli("./examples/example1.wav"),
        help="输入音频文件路径",
    )
    group_debug = parser.add_argument_group("debug", "开发者 debug 使用")
    group_debug.add_argument("--save-response", action="store_true", help="是否保存识别到的 response 到 json 文件")
    group_debug.add_argument("--return-response", action="store_true", help="直接返回 response")

    group_model = parser.add_argument_group("model", "模型参数")
    group_model.add_argument(
        "--only-text", action="store_true", help="是否使用 Model.only_txt(), 更快, 但是没有标点,停顿, 时间线"
    )


def add_punc_recover_arguments(parser: argparse.ArgumentParser, settings: FunASRSettings):
    group_config = parser.add_argument_group("setting", "配置项")
    group_config.add_argument(
        "--device", type=str, default=settings.device, help=f"计算设备(cpu/gpu), 默认为 {settings.device}"
    )
    group_config.add_argument(
        "--punc-model", type=path_from_cli, default=path_from_cli(settings.punc_model), help="分词模型的路径"
    )
    # 这里只加入了需要的参数, 其他的都不需要了

    group_basic = parser.add_argument_group("basic", "基础参数")
    group_basic.add_argument(
        "--input-text",
        "-i",
        type=str,
        help="待恢复标点的文本",
    )


def add_vad_arguments(parser: argparse.ArgumentParser, settings: FunASRSettings):
    group_config = parser.add_argument_group("setting", "配置项")
    group_config.add_argument(
        "--device", type=str, default=settings.device, help=f"计算设备(cpu/gpu), 默认为 {settings.device}"
    )
    group_config.add_argument(
        "--vad-model", type=path_from_cli, default=path_from_cli(settings.vad_model), help="VAD模型的路径"
    )
    group_config.add_argument(
        "--input-path",
        "-i",
        type=path_from_cli,
        default=path_from_cli("./examples/example1.wav"),
        help="输入音频文件路径",
    )

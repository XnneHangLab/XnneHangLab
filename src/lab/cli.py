from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from lab._dataclass import RunnerSettings
from lab.BasicRunner.combiner import combine_sentences
from lab.BasicRunner.converter import (
    calculate_words_length,
    convert_asr_response_to_sentences,
)
from lab.BasicRunner.cutter import cut_sentences
from lab.exceptions import ErrorCode
from lab.utils.config import load_settings_file
from lab.utils.console.logger import Badge, Logger
from lab.utils.model import FunASRModel, generate_asr_results
from lab.utils.SrtHelper import write_srt_from_sentences
from lab.utils.TxtHelper import split_text_into_sentences_by_punctuation_list

if TYPE_CHECKING:
    from lab._typing import DebugMessage


def path_from_cli(path: str) -> Path:
    """从命令行参数获取路径，支持 ~，以便配置中使用 ~"""
    return Path(path).expanduser()


def validate_basic_setting(args: argparse.Namespace):
    """检查传参修改后的基础配置 `global.toml` 的配置项是否存在冲突"""
    Logger.info("正在检查配置项的合法性~")
    # COMBINE_CUT_ERROR
    if args.cut and args.combine:
        Logger.error("并不支持既裁剪(cut=true)又合并(combine=true)噢~")
        sys.exit(ErrorCode.COMBINE_CUT_ERROR.value)
    elif args.cut and not args.combine:
        if args.cut_line < 0:
            Logger.error("cut_line 应该大于 0 ~")
            sys.exit(ErrorCode.COMBINE_CUT_ERROR.value)
    elif not args.cut and args.combine:
        if args.combine_line < 0:
            Logger.error("combine_line 应该大于 0 ~")
            sys.exit(ErrorCode.COMBINE_CUT_ERROR.value)

    # MODEL_FILE_NOT_FOUND_ERROR
    if not args.base_model.exists():
        Logger.error(f"asr_base 模型路径不存在: {args.base_model}")
        sys.exit(ErrorCode.MODEL_FILE_NOT_FOUND_ERROR.value)
    if not args.vad_model.exists():
        Logger.error(f"vad 模型路径不存在: {args.vad_model}")
        sys.exit(ErrorCode.MODEL_FILE_NOT_FOUND_ERROR.value)
    if not args.punc_model.exists():
        Logger.error(f"punc 模型路径不存在: {args.punc_model}")
        sys.exit(ErrorCode.MODEL_FILE_NOT_FOUND_ERROR.value)

    # TODO FFmpeg 应该也得找个地方验证一下, 但是在这里运行可能耗时太长了.

def valid_model_args(args: argparse.Namespace):
    """检查 group_model 是否存在冲突"""
    # 只能存在一个, 多个警告
    if int(args.only_text) + int(args.only_vad) + int(args.only_punc) + int(args.vad_and_asr) > 1:
        Logger.error(
            "只允许至多选择一种模型参数, 其他的会被忽略, 请检查你的参数设置~"
            f"only_text: {args.only_text}, only_vad: {args.only_vad}, only_punc: {args.only_punc}, vad_and_asr: {args.vad_and_asr}"
        )
        sys.exit(ErrorCode.MODEL_SELECTION_ERROR.value)
    if int(args.only_text) + int(args.only_vad) + int(args.only_punc) + int(args.vad_and_asr) == 0:
        Logger.info(
            "默认使用 asr+vad+punc 模型, 如果你希望使用其他模型, 请查看 model_args 的参数设置~"
        )

def show_args(args: argparse.Namespace):
    for key, value in vars(args).items():
        Logger.custom(value, Badge(key, fore="green"))


# 定义长文本写入函数
def main():
    parser = argparse.ArgumentParser(description="将wav音频转换成srt")
    settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)
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
    group_basic.add_argument(
        "-o",
        "--output_path",
        type=path_from_cli,
        default=path_from_cli("./output/example1.srt"),
        help="输出 srt 文件路径",
    )
    group_debug = parser.add_argument_group("debug", "开发者 debug 使用")
    group_debug.add_argument("--debug", action="store_true", help="是否开启debug模式")
    group_debug.add_argument("--show-config", action="store_true", help="是否打印配置项")
    group_debug.add_argument("--save-text", action="store_true", help="是否保存识别到的文本文件")
    group_debug.add_argument(
        "--save-asr-response", action="store_true", help="是否保存识别到的 asr_response 到 json 文件"
    )
    group_debug.add_argument(
        "--return-asr-response", action="store_true", help="是否保存识别到的 asr_response 到 json 文件"
    )

    group_model = parser.add_argument_group("model", "模型参数")
    group_model.add_argument(
        "--only-text", action="store_true", help="是否使用 Model.only_txt(), 更快, 但是没有标点和停顿"
    )
    group_model.add_argument(
        "--only-vad", action="store_true", help="是否使用 Model.only_vad(), 只进行语音活动检测, 不进行识别"
    )
    group_model.add_argument(
        "--only-punc", action="store_true", help="是否使用 Model.only_puc(), 只进行标点检测, 不进行识别"
    )
    group_model.add_argument(
        "--vad-and-asr", action="store_true", help="是否使用 Model.vad_and_asr(), 先进行语音活动检测, 再进行识别, 无标点"
    )
    # 读取 group_config 的参数
    args = parser.parse_args()

    # 允许用户临时修改配置项, 但不会更改到 global.toml 中
    validate_basic_setting(args)
    valid_model_args(args)
    if args.show_config:
        cfg_keys = [a.dest for a in group_config._group_actions]
        group_config_args = argparse.Namespace(**{k: getattr(args, k) for k in cfg_keys})
        Logger.custom("加载配置项...", Badge("配置", fore="black", back="cyan"))
        show_args(group_config_args)

    Model = FunASRModel()
    if args.only_text:
        model = Model.only_txt()  # 似乎更快了一点, 但是没了标点 0.7s -> 0.55s.
    elif args.only_vad:
        model = Model.only_vad()
    elif args.only_punc:
        model = Model.only_puc()
    elif args.vad_and_asr:
        model = Model.vad_and_asr()
    else:
        model = Model.asr_full_version()

    start = time.time()
    response = generate_asr_results(model=model, input_path=args.input_path)
    end = time.time()

    if args.save_text:
        Path("rec.txt").write_text(response["text"], encoding="utf-8")

    if args.save_asr_response:
        json_str = json.dumps(response, indent=4, ensure_ascii=False)
        Path("asr_response.json").write_text(json_str, encoding="utf-8")

    if args.return_asr_response:
        return response

    if args.debug:  # TODO: 实际上这个执行的是独立任务, 如果 main() 变得过于复杂,可以把它拆到独立的 pyproject.script
        Logger.info("正在使用 Debug 模式, 该模式直接打印调试信息~")
        Logger.info(f"ASR 实际耗时: {end - start:.2f}秒")
        segmented_text = split_text_into_sentences_by_punctuation_list(response["text"])
        total_words_num = 0
        for sentence in segmented_text:
            # 把英文单词作为一个汉字长度来计算。
            total_words_num += calculate_words_length(sentence)
        debug_message: DebugMessage = {
            "segmented_text": segmented_text,
            "total_words_num": total_words_num,
            "total_ts_num": len(response["timestamp"]),
        }
        # 比对长度，如果不一样，说明有多余的未加入的符号。并且这个符号被计入 total_words_num 中。 这时候就会出现 list index out of range 的错误。 可以通过排查该符号然后加入 punc_list 来解决。
        Logger.info(debug_message)
    else:
        # TODO: 设置 Logger 告知用户自己正在使用哪种模式.
        sentences = convert_asr_response_to_sentences(response)
        # 参数合法性在 validate_basic_setting 中已经检查过了
        if settings.cut and not settings.combine:
            sentences = cut_sentences(sentences=sentences, cutline=settings.combine_line)
        elif not settings.cut and settings.combine:
            sentences = combine_sentences(
                sentences=sentences,
                combine_line=settings.combine_line,
                max_sentence_length=settings.max_sentence_length,
            )
        else:  # 不裁剪也不合并
            pass
        write_srt_from_sentences(sentences=sentences, srt_file_path=args.output_path)

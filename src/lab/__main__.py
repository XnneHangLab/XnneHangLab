from __future__ import annotations

# from time import time
import json
import sys
from typing import TYPE_CHECKING

from lab.asr.combiner import combine_sentences
from lab.asr.cutter import cut_sentences
from lab.asr.funasr.converter import convert_asr_response_to_sentences
from lab.asr.funasr.method import generate_asr_results, generate_punc_results, generate_vad_results
from lab.asr.funasr.model import FunASRModel
from lab.cli import cli, handle_default_subcommand

# from lab.exceptions import ErrorCode
from lab.utils.console.logger import Badge, Logger
from lab.utils.SrtHelper import write_srt_from_sentences
from lab.validator import validate_recognizer_args, validate_setting_args

if TYPE_CHECKING:
    import argparse

    from lab._typing import ASRResponse, Sentence, VadResponse


def main():
    parser = cli()
    args = parser.parse_args(handle_default_subcommand(sys.argv[1:]))
    Model = FunASRModel()
    match args.command:
        case "recognize":
            validate_setting_args(args)
            validate_recognizer_args(args)
            # try:
            run_recognizer(args, Model)
            # except (SystemExit, KeyboardInterrupt, asyncio.exceptions.CancelledError):
            #     Logger.info("已终止下载，再次运行即可继续下载～")
        case "punc_recover":
            run_punc_recover(args, Model)
        case "vad":
            run_vad(args, Model)
        case _:
            raise ValueError("Invalid command")


def run_punc_recover(args: argparse.Namespace, Model: FunASRModel):
    Logger.custom("标点恢复", badge=Badge("任务", fore="black", back="cyan"))
    model = Model.only_puc()  # 这一步还是有点时间在的 =- =, 如果极限压缩, 那么请考虑把它作为全局变量
    res = generate_punc_results(model, args.input_text)
    print(res)


def run_vad(args: argparse.Namespace, Model: FunASRModel):
    Logger.custom("VAD 语音活动检测", badge=Badge("任务", fore="black", back="cyan"))
    model = Model.only_vad()  # 这一步还是有点时间在的 =- =, 如果极限压缩, 那么请考虑把它作为全局变量
    response: VadResponse = generate_vad_results(model, args.input_path)
    Logger.info(response)


def run_recognizer(args: argparse.Namespace, Model: FunASRModel):
    Logger.custom("识别音频文件", badge=Badge("任务", fore="black", back="cyan"))
    # 加载模型, 同理, 如果极限压缩(不想要每次使用卡加载模型的时间), 那么请考虑把它作为全局变量在运行前加载
    # 比如你作为 fastapi 的一个 endpoint. 那么请考虑作为全局变量在 lifespan 中加载
    if args.only_text:
        model = Model.only_txt()
    else:
        model = Model.vad_and_asr()

    response: ASRResponse = generate_asr_results(model, args.input_path)

    if args.save_response:
        save_str = json.dumps(response, ensure_ascii=False, indent=4)
        save_path = args.output_dir / f"{args.input_path.stem}.json"
        with save_path.open("w", encoding="utf-8") as f:
            f.write(save_str)

    if args.return_response:
        return response

    sentences: list[Sentence] = convert_asr_response_to_sentences(response)

    if args.cut:
        sentences = cut_sentences(sentences=sentences, cut_line=args.cut_line)
    elif args.combine:
        sentences = combine_sentences(
            sentences=sentences, combine_line=args.combine_line, max_sentence_length=args.max_sentence_length
        )
    else:
        pass

    # 将 sentences 写入 srt 文件
    srt_file_path = args.output_dir / f"{args.input_path.stem}.srt"
    write_srt_from_sentences(sentences=sentences, srt_file_path=srt_file_path)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from lab._dataclass import RunnerSettings
from lab.BasicRunner.combiner import combine_sentences
from lab.BasicRunner.converter import (
    calculate_words_length,
    convert_asr_response_to_sentences,
)
from lab.BasicRunner.cutter import cut_sentences
from lab.utils.config import load_settings_file
from lab.utils.console.logger import Logger
from lab.utils.model import FunASRModel, generate_asr_results
from lab.utils.SrtHelper import write_srt_from_sentences
from lab.utils.TxtHelper import split_text_into_sentences_by_punctuation_list

if TYPE_CHECKING:
    from lab._typing import ASRResponse, DebugMessage


# 定义长文本写入函数
def main():
    argparser = argparse.ArgumentParser(description="将wav音频转换成srt")
    argparser.add_argument("-i", "--input_path", default="./examples/example1.wav", help="输入音频文件")
    argparser.add_argument("-o", "--output_path", default="./output/example1.srt", help="输出srt文件")
    # argparser.add_argument("--only-text", store_true, help="是否只输出文本")
    argparser.add_argument("--debug", action="store_true", help="是否开启debug模式")

    args = argparser.parse_args()
    audio_file_path = Path(args.input_path)
    srt_file_path = Path(args.output_path)
    debug = args.debug
    if debug:
        Logger.info("Debug 模式不会写入 srt 文件, 而是直接打印~")

    Model = FunASRModel()
    model = Model.asr_full_version()

    settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)

    response: ASRResponse = generate_asr_results(model=model, input_path=audio_file_path)

    if debug:
        # 应该写入，然后查找是否有除了中英文之外的符号。最后加入 config.punctuation_list
        print(split_text_into_sentences_by_punctuation_list(response["text"]))
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
        # 比对长度，如果不一样，说明有多余的未加入的符号。并且这个符号被计入 total_words_num 中。
        Logger.info(debug_message)
    else:
        # TODO: 设置 Logger 告知用户自己正在使用哪种模式.
        sentences = convert_asr_response_to_sentences(response)
        if settings.cut and settings.combine:
            if settings.combine_line < settings.cut_line:
                raise ValueError("combine_line should be greater than cut_line, or all cut will be ignored.")
        elif settings.cut and not settings.combine:
            if settings.combine_line < 0:
                raise ValueError("cut_line should be greater than 0.")
            sentences = cut_sentences(sentences=sentences, cutline=settings.combine_line)
        elif not settings.cut and settings.combine:
            if settings.combine_line < 0:
                raise ValueError("combine_line should be greater than 0.")
            sentences = combine_sentences(
                sentences=sentences,
                combine_line=settings.combine_line,
                max_sentence_length=settings.max_sentence_length,
            )
        else:
            pass
        write_srt_from_sentences(sentences=sentences, srt_file_path=srt_file_path)

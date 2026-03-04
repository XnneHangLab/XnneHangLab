from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import funasr
import torch
import torchaudio
from todo.__version__ import VERSION  # type: ignore[reportMissingImports,reportUnknownVariableType]

from lab.asr.funasr.method import generate_asr_results, generate_sense_voice_results
from lab.asr.funasr.model import FunASRModel
from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.utils.TxtHelper import split_into_words, split_into_words_no_punct

if TYPE_CHECKING:
    from lab._typing import SenseVoiceResponse


def main():
    print("====== testing audio ========")
    testing_file = Path("./examples/example1.wav")
    if not testing_file.exists():
        raise FileNotFoundError(f"File not found: {testing_file}")

    print("====== Version =======")
    print(f"funasr:{funasr.__version__}")
    print(f"torch:{torch.__version__}")
    print(f"torchaudio:{torchaudio.__version__}")

    print("====== Testing package_todo =======")
    print(f"todo:{VERSION}")

    # print("====== Testing fn_call_test_ffmpeg ======")
    # test_call_ffmpeg()

    # print("====== Testing fn_convert_asr_response_to_sentences =======")

    # Model = FunASRModel()
    # model = Model.vad_and_asr()
    # response = generate_asr_results(model=model, input_path=testing_file)
    # save_only_text_from_response(response=response, output_dir=Path("./output"))

    # print("====== Testing fn_convert_asr_response_to_sentences =======")
    # sentences: list[Sentence] = convert_asr_response_to_sentences(response)

    # print("====== Testing fn_split_into_words =======")
    # print(split_into_words("晚安纳尼南尼nony!"))  # ['晚', '安', '纳', '尼', '南', '尼', 'nony']
    # print(split_into_words("就的真的妈a等等?"))  # ['就', '的', '真', '的', '妈', 'a', '等', '等']
    # print(split_into_words("多喜天dustin birthday."))  # ['多', '喜', '天', 'dustin', 'birthday']
    # print(split_into_words("He's 我见过的。"))  # ["He's", '我', '见', '过', '的', '。']

    # print("====== Testing fn_split_into_words_no_punct =======")
    # # TODO 当到了 testing 的时候，应该对比输出的 textlist 和 timestamp 的长度
    # print(split_into_words_no_punct("晚安纳尼南尼nony!"))  # ['晚', '安', '纳', '尼', '南', '尼', 'nony']
    # print(split_into_words_no_punct("就的真的妈a等等?"))  # ['就', '的', '真', '的', '妈', 'a', '等', '等']
    # print(split_into_words_no_punct("多喜天dustin birthday."))  # ['多', '喜', '天', 'dustin', 'birthday']
    # print(split_into_words_no_punct("He's 我见过的。"))  # ["He's", '我', '见', '过', '的', '。']

    # print("====== Testing non-process-wav2srt =======")
    # write_srt_from_sentences(sentences=sentences, srt_file_path=Path("./output/test.srt"))

    # print("====== Testing cut wav2srt")
    # cut_sentences(sentences=sentences, cutline=500)

    # print("====== Testing combine wav2srt")
    # combine_sentences(sentences=sentences, combine_line=500, max_sentence_length=500)

    print("====== Testing generate_sense_voice_results =======")
    settings = load_settings_file("lab.toml", XnneHangLabSettings)
    punctuation_list = settings.asr.funasr.punctuation_list

    print("====== Testing generate_sense_voice_results =======")
    # TODO https://github.com/FunAudioLLM/SenseVoice/issues/204
    # TODO 另外，标点符号也具有 timestamp， 所以 SenseVoice 的标点不应该被过滤掉
    Model = FunASRModel()
    model = Model.vad_and_asr()

    response = generate_asr_results(model=model, input_path=testing_file)
    asr_text = response["text"]
    asr_timestamp = response["timestamp"]

    model = Model.sense_voice()
    response = generate_sense_voice_results(model=model, input_path=Path(testing_file))
    key = response["key"]
    sense_text = response["text"]
    sense_timestamp = response["timestamp"]

    #    这个正则表达式捕获两部分：
    #    Group 1: ((?:<\|[^|]+\|>){4}) - 捕获连续的四个标签
    #    Group 2: (.*?) - 非贪婪地捕获标签后面的所有文本...
    #    ...直到遇到下一个四个标签的开始 (?=(?:<\|[^|]+\|>){4}) 或者字符串结尾 ($)
    pattern = re.compile(
        r"((?:<\|[^|]+\|>){4})"  # Group 1: The four tags
        r"\s*"  # Optional whitespace after tags
        r"(.*?)"  # Group 2: The text (non-greedy)
        r"(?=(?:<\|[^|]+\|>){4}|$)",  # Positive lookahead for next 4 tags or end of string
        re.DOTALL,  # Allow '.' to match newline characters
    )

    results: list[SenseVoiceResponse] = []
    only_text = ""
    matches = pattern.findall(sense_text)
    sentence_length = 0

    for status_tags, sentence_text in matches:
        cleaned_sentence = sentence_text.strip()
        # Since timestamp data isn't provided, we'll use an empty list as a placeholder.
        # The verification step will calculate word count based on 'sentences'.
        segment_dict: SenseVoiceResponse = {
            "key": key,
            "status": status_tags,
            "text": cleaned_sentence,
            "timestamp": sense_timestamp[
                sentence_length : len(split_into_words(cleaned_sentence))
            ],  # TODO 如果标点时间戳后续被过滤掉，这里需要修改为 split_into_words_no_punct
        }
        sentence_length += len(split_into_words(cleaned_sentence))
        results.append(segment_dict)
        only_text += cleaned_sentence

    sense_text_list = split_into_words_no_punct(only_text)
    asr_text_list = split_into_words_no_punct(asr_text)
    sense_text_with_punc_list = split_into_words(only_text)
    asr_text_with_punc_list = split_into_words(asr_text)

    sense_punc_num = 0
    for word in sense_text_with_punc_list:
        if word in punctuation_list:
            sense_punc_num += 1
    asr_punc_num = 0
    for word in asr_text_with_punc_list:
        if word in punctuation_list:
            asr_punc_num += 1

    print("=" * 20)
    print(f"SenseVoice text:            {sense_text}")
    print(f"SenseVoice text:(no status):{only_text}")
    print(f"SeACoParaformer:            {asr_text}")
    print(f"SenseVoice timestamp: {sense_timestamp}")
    print(f"ASR timestamp:        {asr_timestamp}")

    print("=" * 20)
    print(f"SenseVoice WORD List(no punc):  {sense_text_list}")
    print(f"SenseVoice WORD List(with punc):{sense_text_with_punc_list}")
    print(f"ASR WORD List(no punc):         {asr_text_list}")
    print(f"ASR WORD List(with punc):       {asr_text_with_punc_list}")

    print("=" * 20)
    print(f"SenseVoice 识别到的 WORD 数(no punc):  {len(sense_text_list)}")
    print(f"SenseVoice 识别到的 WORD 数(with punc):{len(sense_text_with_punc_list)}")
    print(f"ASR 识别到的 WORD 数(no punc):         {len(asr_text_list)}")
    print(f"ASR 识别到的 WORD 数(with punc):       {len(asr_text_with_punc_list)}")

    print("=" * 20)
    print(f"SenseVoice 识别到的标点数:             {sense_punc_num}")
    print(f"ASR 识别到的标点数:                    {asr_punc_num}")

    print("=" * 20)
    print(f"SenseVoice 识别到的 timestamp 数:      {len(sense_timestamp)}")
    print(f"ASR 识别到的 timestamp 数:             {len(asr_timestamp)}")

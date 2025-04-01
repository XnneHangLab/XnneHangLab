from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING
import json

import funasr
import torch
import torchaudio
from todo.__version__ import VERSION

from uiya._dataclass import AudioSettings, RunnerSettings
from uiya.BasicRunner.combiner import combine_sentences
from uiya.BasicRunner.converter import convert_asr_response_to_sentences, split_into_words
from uiya.BasicRunner.cutter import cut_sentences
from uiya.BasicRunner.extractor import save_only_text_from_response
from uiya.utils.config import get_setting_title, load_settings_file
from uiya.utils.FFmpegHelper import test_call_ffmpeg
from uiya.utils.model import FunASRModel, generate_asr_results,generate_sense_voice_results
from uiya.utils.SrtHelper import write_srt_from_sentences

if TYPE_CHECKING:
    from uiya._typing import Sentence


def main():
    print("====== Version =======")
    print(f"funasr:{funasr.__version__}")
    print(f"torch:{torch.__version__}")
    print(f"torchaudio:{torchaudio.__version__}")

    print("====== Testing package_todo =======")
    print(f"todo:{VERSION}")

    print("====== Testing fn_load_settings_file =======")
    settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)
    print(settings)
    audio_settings: AudioSettings = load_settings_file("audio.toml", AudioSettings)
    print(audio_settings)

    print("====== Testing fn_get_setting_title=======")
    print("subtitle -> " + get_setting_title("subtitle_speed", AudioSettings))
    print("device -> " + get_setting_title("device", RunnerSettings))
    print("base_model -> " + get_setting_title("base_model", RunnerSettings))

    print("====== Testing fn_call_test_ffmpeg ======")
    test_call_ffmpeg()

    print("====== Testing fn_convert_asr_response_to_sentences =======")
    parser = argparse.ArgumentParser(description="将wav音频转换成srt")
    parser.add_argument("-i", "--input_path", default="./tests/example1.wav", help="输入音频文件")
    args = parser.parse_args()

    Model = FunASRModel()
    model = Model.asr_full_version()
    response = generate_asr_results(model=model, input_path=Path(args.input_path))
    save_only_text_from_response(response=response, output_dir=Path("./output"))

    print("====== Testing fn_convert_asr_response_to_sentences =======")
    sentences: list[Sentence] = convert_asr_response_to_sentences(response)

    print("====== Testing fn_split_into_words =======")
    print(split_into_words("晚安纳尼南尼nony!"))  # ['晚', '安', '纳', '尼', '南', '尼', 'nony']
    print(split_into_words("就的真的妈a等等?"))  # ['就', '的', '真', '的', '妈', 'a', '等', '等']
    print(split_into_words("多喜天dustin birthday."))  # ['多', '喜', '天', 'dustin', 'birthday']
    print(split_into_words("He's 我见过的。"))  # ["He's", '我', '见', '过', '的', '。']

    print("====== Testing non-process-wav2srt =======")
    write_srt_from_sentences(sentences=sentences, srt_file_path=Path("./output/test.srt"))

    print("====== Testing cut wav2srt")
    cut_sentences(sentences=sentences, cutline=500)

    print("====== Testing combine wav2srt")
    combine_sentences(sentences=sentences, combine_line=500, max_sentence_length=500)

    print("====== Testing generate_sense_voice_results =======")
    Model = FunASRModel()
    model = Model.sense_voice()
    response = generate_asr_results(model=model, input_path=Path("./tests/example1.wav"))
    print(response)
    with open("./output/response.json", "w") as f:
        json.dump(response, f, ensure_ascii=False, indent=4)
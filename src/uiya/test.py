import funasr
import torch
import torchaudio
import argparse
from pathlib import Path

from uiya.utils.model import FunASRModel, generate_results
from uiya.utils.TxtHelper import save_only_text_from_response


def main():
    print(f"funasr:{funasr.__version__}")
    print(f"torch:{torch.__version__}")
    print(f"torchaudio:{torchaudio.__version__}")

    parser = argparse.ArgumentParser(description="将wav音频转换成srt")
    parser.add_argument(
        "-i", "--input_path", default="./example.wav", help="输入音频文件"
    )
    args = parser.parse_args()

    Model = FunASRModel()
    model = Model.full_version()
    response = generate_results(
        model=model, input_path=Path(args.input_path), hot_word="", debug=True
    )
    save_only_text_from_response(response=response, output_dir=Path("./test"))

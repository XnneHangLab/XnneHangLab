import funasr
import torch
import torchaudio

from uiya.BasicRunner.converter import split_into_words


def main():
    print(f"funasr:{funasr.__version__}")
    print(f"torch:{torch.__version__}")
    print(f"torchaudio:{torchaudio.__version__}")

    # === test save_only_text_from_response ===
    # parser = argparse.ArgumentParser(description="将wav音频转换成srt")
    # parser.add_argument(
    #     "-i", "--input_path", default="./example.wav", help="输入音频文件"
    # )
    # args = parser.parse_args()

    # Model = FunASRModel()
    # model = Model.full_version()
    # response = generate_results(
    #     model=model, input_path=Path(args.input_path), hot_word="", debug=True
    # )
    # save_only_text_from_response(response=response, output_dir=Path("./test"))

    # === test convert_response_to_sentences ===

    # === test split_into_words ===
    # print(convert_format(input_data,debug=True))
    print(
        split_into_words("晚安纳尼南尼nony!")
    )  # ['晚', '安', '纳', '尼', '南', '尼', 'nony']
    print(
        split_into_words("就的真的妈a等等?")
    )  # ['就', '的', '真', '的', '妈', 'a', '等', '等']
    print(
        split_into_words("多喜天dustin birthday.")
    )  # ['多', '喜', '天', 'dustin', 'birthday']
    print(split_into_words("He's 我见过的。"))  # ["He's", '我', '见', '过', '的', '。']

import funasr
import torch
import torchaudio

from uiya.BasicRunner.converter import split_into_words

# import cProfile


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

    # response: AutoModelResponse = AutoModelResponse(
    #     key="example",
    #     text="你今天可真是cute呢!",
    #     timestamp=[
    #         [0, 300],
    #         [300, 540],
    #         [540, 600],
    #         [600, 900],
    #         [900, 1200],
    #         [1200, 1500],
    #         [1500, 2200],
    #         [2200, 2500],
    #     ],
    # )
    # sentence: list[Sentence] = convert_response_to_sentences(response)
    # print(sentence[0]["text"])
    # print(sentence[0]["Words"])

    # === test split_into_words ===
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

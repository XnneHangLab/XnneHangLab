from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lab._dataclass import RunnerSettings
from lab.BasicRunner.converter import split_into_words, split_into_words_no_punct
from lab.utils.config import load_settings_file
from lab.utils.model import FunASRModel, generate_sense_voice_results

if TYPE_CHECKING:
    from typing import Any

    from funasr import AutoModel

    from lab._typing import ASRResponse, SenseVoiceResponse


# 会话级别的fixtures
@pytest.fixture(scope="session")
def testing_file():
    file_path = Path("./examples/example1.wav")
    if not file_path.exists():
        pytest.skip(f"File not found: {file_path}")
    return file_path


@pytest.fixture(scope="session")
def punctuation_list():
    settings = load_settings_file("global.toml", RunnerSettings)
    return settings.punctuation_list


@pytest.fixture(scope="session")
def sense_voice_model():
    Model = FunASRModel()
    return Model.sense_voice()


@pytest.fixture(scope="session")
def sense_voice_response(testing_file: Path, sense_voice_model: AutoModel) -> ASRResponse:
    """生成SenseVoice响应，整个测试会话只执行一次"""
    return generate_sense_voice_results(model=sense_voice_model, input_path=testing_file)


@pytest.fixture(scope="session")
def parsed_sense_voice_data(sense_voice_response: ASRResponse) -> dict[str, Any]:
    """解析SenseVoice响应，整个测试会话只执行一次"""
    key = sense_voice_response["key"]
    sense_text = sense_voice_response["text"]
    sense_timestamp = sense_voice_response["timestamp"]

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
        segment_dict: SenseVoiceResponse = {
            "key": key,
            "status": status_tags,
            "text": cleaned_sentence,
            "timestamp": sense_timestamp[sentence_length : sentence_length + len(split_into_words(cleaned_sentence))],
        }
        sentence_length += len(split_into_words(cleaned_sentence))
        results.append(segment_dict)
        only_text += cleaned_sentence

    # 预计算文本列表和标点符号数量
    sense_text_list = split_into_words_no_punct(only_text)
    sense_text_with_punc_list = split_into_words(only_text)

    return {
        "results": results,
        "only_text": only_text,
        "sense_text_list": sense_text_list,
        "sense_text_with_punc_list": sense_text_with_punc_list,
        "sense_timestamp": sense_timestamp,
    }


class TestSenseVoice:
    """测试SenseVoice功能"""

    def test_file_exists(self, testing_file: Path):
        """测试音频文件存在"""
        assert testing_file.exists(), f"File not found: {testing_file}"

    def test_timestamp_matches_words(self, parsed_sense_voice_data: dict[str, Any]):
        """测试时间戳数量与单词数量匹配"""
        sense_text_list = parsed_sense_voice_data["sense_text_list"]
        sense_timestamp = parsed_sense_voice_data["sense_timestamp"]

        assert len(sense_text_list) == len(sense_timestamp), (
            f"Words count: {len(sense_text_list)}, timestamps count: {len(sense_timestamp)}"
        )

    def test_sense_voice_punctuation_count(self, parsed_sense_voice_data: dict[str, Any], punctuation_list: str):
        """测试标点符号计数"""
        sense_text_with_punc_list = parsed_sense_voice_data["sense_text_with_punc_list"]

        sense_punc_num = sum(1 for word in sense_text_with_punc_list if word in punctuation_list)

        # 这里不做断言，只打印信息
        print(f"\nSenseVoice punctuation count: {sense_punc_num}")
        print(f"Total words with punctuation: {len(sense_text_with_punc_list)}")
        print(f"Total words without punctuation: {len(parsed_sense_voice_data['sense_text_list'])}")

if __name__ == "__main__":
    pytest.main(["-v", __file__])
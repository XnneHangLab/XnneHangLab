from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lab._dataclass import AudioSettings, RunnerSettings
from lab.BasicRunner.combiner import combine_sentences
from lab.BasicRunner.converter import convert_asr_response_to_sentences, split_into_words, split_into_words_no_punct
from lab.BasicRunner.cutter import cut_sentences
from lab.BasicRunner.extractor import save_only_text_from_response
from lab.utils.config import get_setting_title, load_settings_file
from lab.utils.FFmpegHelper import test_call_ffmpeg
from lab.utils.model import FunASRModel, generate_asr_results
from lab.utils.SrtHelper import write_srt_from_sentences

if TYPE_CHECKING:
    from funasr import AutoModel

    from lab._typing import ASRResponse, Sentence


# 会话级别的fixture - 只执行一次
@pytest.fixture(scope="session")
def testing_file():
    file_path = Path("./examples/example1.wav")
    if not file_path.exists():
        pytest.skip(f"File not found: {file_path}")
    return file_path


@pytest.fixture(scope="session")
def asr_model():
    Model = FunASRModel()
    return Model.asr_full_version()


@pytest.fixture(scope="session")
def asr_response(testing_file: Path, asr_model: AutoModel) -> ASRResponse:
    """只执行一次的ASR响应生成"""
    return generate_asr_results(model=asr_model, input_path=testing_file)


@pytest.fixture(scope="session")
def sentences(asr_response: ASRResponse) -> list[Sentence]:
    """基于ASR响应生成句子，也只执行一次"""
    return convert_asr_response_to_sentences(asr_response)


# 为每个测试准备输出目录
@pytest.fixture(scope="session", autouse=True)
def prepare_output_dir():
    Path("./output").mkdir(exist_ok=True)


class TestLabComponents:
    """测试Lab组件的各项功能"""

    # 简化后的setup - 只注入依赖项
    @pytest.fixture(autouse=True)
    def setup(self, testing_file: Path, asr_response: ASRResponse, sentences: list[Sentence]):
        """设置测试环境,注入会话级别的fixture"""
        self.testing_file: Path = testing_file
        self.response = asr_response
        self.sentences = sentences
        yield

    def test_audio_file_exists(self):
        """测试音频文件存在"""
        assert self.testing_file.exists(), f"File not found: {self.testing_file}"

    def test_load_settings_file(self):
        """测试加载设置文件"""
        load_settings_file("global.toml", RunnerSettings)
        assert Path("config/global.toml").exists(), "global.toml not create successfully"
        load_settings_file("audio.toml", AudioSettings)
        assert Path("config/audio.toml").exists(), "audio.toml not create successfully"

    def test_get_setting_title(self):
        """测试获取设置标题"""
        assert get_setting_title("subtitle_speed", AudioSettings) == "字幕速度"
        assert get_setting_title("device", RunnerSettings) == "设备选择"
        assert get_setting_title("base_model", RunnerSettings) == "base 模型"

    def test_ffmpeg(self):
        """测试ffmpeg可用性"""
        assert test_call_ffmpeg() is True, "ffmpeg not available"

    def test_save_only_text_from_response(self):
        """测试保存文本响应"""
        save_only_text_from_response(response=self.response, output_dir=Path("./output"))
        assert Path("./output/example1_only_text.txt").exists(), "example1.txt not create successfully"

    def test_convert_asr_response_to_sentences(self):
        """测试转换ASR响应到句子"""
        assert isinstance(self.sentences, list)
        for sentence in self.sentences:
            assert "Words" in sentence
            assert isinstance(sentence["Words"], list)

    def test_split_into_words(self):
        """测试分词函数"""
        assert split_into_words("晚安纳尼南尼nony!") == ["晚", "安", "纳", "尼", "南", "尼", "nony", "!"]
        assert split_into_words("就的真的妈a等等?") == ["就", "的", "真", "的", "妈", "a", "等", "等", "?"]
        assert split_into_words("多喜天dustin birthday.") == ["多", "喜", "天", "dustin", "birthday", "."]
        assert split_into_words("He's 我见过的。") == ["He's", "我", "见", "过", "的", "。"]

    def test_split_into_words_no_punct(self):
        """测试无标点分词函数"""
        assert split_into_words_no_punct("晚安纳尼南尼nony!") == ["晚", "安", "纳", "尼", "南", "尼", "nony"]
        assert split_into_words_no_punct("就的真的妈a等等?") == ["就", "的", "真", "的", "妈", "a", "等", "等"]
        assert split_into_words_no_punct("多喜天dustin birthday.") == ["多", "喜", "天", "dustin", "birthday"]
        assert split_into_words_no_punct("He's 我见过的。") == ["He's", "我", "见", "过", "的"]

    def test_write_srt_from_sentences(self):
        """测试SRT文件生成"""
        output_path = Path("./output/test.srt")
        write_srt_from_sentences(sentences=self.sentences, srt_file_path=output_path)
        assert output_path.exists(), "test.srt not create successfully"

    def test_sentence_processing_consistency(self):
        """测试句子处理一致性"""
        # 原始总长度
        original_total_length = sum(len(sentence["Words"]) for sentence in self.sentences)

        # 测试切割句子
        cutted_sentences = cut_sentences(sentences=self.sentences, cutline=500)
        cutted_total_length = sum(len(sentence["Words"]) for sentence in cutted_sentences)

        # 测试组合句子
        combined_sentences = combine_sentences(sentences=self.sentences, combine_line=500, max_sentence_length=500)
        combined_total_length = sum(len(sentence["Words"]) for sentence in combined_sentences)

        # 验证长度一致性
        assert original_total_length == cutted_total_length == combined_total_length


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

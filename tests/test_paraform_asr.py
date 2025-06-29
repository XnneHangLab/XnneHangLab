from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lab.__main__ import main as basic_runner
from lab.config_manager import AudioRecognizeSettings, FunASRSettings, get_setting_title, load_settings_file
from lab.utils.FFmpegHelper import test_call_ffmpeg


class TestLabComponents:
    """测试Lab组件的各项功能"""

    testing_file = Path("./examples/example1.wav")
    # 简化后的setup - 只注入依赖项

    def test_audio_file_exists(self):
        """测试音频文件存在"""
        assert self.testing_file.exists(), f"File not found: {self.testing_file}"

    def test_load_settings_file(self):
        """测试加载设置文件"""
        load_settings_file("funasr.toml", FunASRSettings)
        assert Path("config/funasr.toml").exists(), "funasr.toml not create successfully"
        load_settings_file("audio.toml", AudioRecognizeSettings)
        assert Path("config/audio.toml").exists(), "audio.toml not create successfully"

    def test_get_setting_title(self):
        """测试获取设置标题"""
        assert get_setting_title("subtitle_speed", AudioRecognizeSettings) == "字幕速度"
        assert get_setting_title("device", FunASRSettings) == "设备选择"
        assert get_setting_title("base_model", FunASRSettings) == "base 模型"

    def test_ffmpeg(self):
        """测试ffmpeg可用性"""
        assert test_call_ffmpeg() is True, "ffmpeg not available"

    def test_convert_asr_response_to_sentences(self):
        # 模拟命令行参数
        sys.argv = [
            "",  # 必要的占位 solving error: unrecognized arguments:
            "--input_path",
            str(self.testing_file),  # 输入音频文件路径
        ]

        # 调用 basic_runner (即 main 函数)
        response = basic_runner()  # type: ignore


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

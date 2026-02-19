from __future__ import annotations

from pathlib import Path

import pytest

from lab.config_manager import XnneHangLabSettings, load_settings_file


class TestLabComponents:
    """测试Lab组件的各项功能"""

    testing_file = Path("./examples/example1.wav")
    # 简化后的setup - 只注入依赖项

    def test_audio_file_exists(self):
        """测试音频文件存在"""
        assert self.testing_file.exists(), f"File not found: {self.testing_file}"

    def test_load_settings_file(self):
        """测试加载设置文件"""
        load_settings_file("lab.toml", XnneHangLabSettings)
        assert Path("config/lab.toml").exists(), "lab.toml not create successfully"

    # def test_get_setting_title(self):
    #     """测试获取设置标题"""
    # TODO 改用 i18n 实现。
    #     assert get_setting_title("subtitle_speed", AudioRecognizeSettings) == "字幕速度"
    #     assert get_setting_title("device", FunASRSettings) == "设备选择"
    #     assert get_setting_title("base_model", FunASRSettings) == "base 模型"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

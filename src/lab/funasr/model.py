from __future__ import annotations

from funasr import AutoModel

from lab.config_manager import XnneHangLabSettings, load_settings_file


class FunASRModel:
    def __init__(self):
        self.settings = load_settings_file("lab.toml", XnneHangLabSettings)
        self.base_model: str = str(self.settings.funasr.base_model)
        self.vad_model: str = str(self.settings.funasr.vad_model)
        self.punc_model: str = str(self.settings.funasr.punc_model)
        self.sense_voice_model: str = str(self.settings.funasr.sense_voice_model)
        self.device: str = self.settings.funasr.device

    def sense_voice(self):
        model = AutoModel(
            model=self.sense_voice_model,
            vad_model=self.vad_model,  # vad 是用于音频分段的
            vad_kwargs={"max_single_segment_time": 30000},
            device=self.device,
            disable_update=True,
        )
        return model

    def vad_and_asr(self):
        model = AutoModel(
            model=self.base_model,  # base
            vad_model=self.vad_model,  # 检测语音活动，自动分隔
            device=self.device,
            disable_update=True,  # 添加在这里，禁用更新检查
        )
        return model

    def only_txt(self):
        model = AutoModel(model=self.base_model, device=self.device, disable_update=True)  # 也可以添加在这里
        return model

    def only_puc(self):
        model = AutoModel(model=self.punc_model, device=self.device, disable_update=True)  # 也可以添加在这里
        return model

    def only_vad(self):
        model = AutoModel(
            model=self.vad_model,
            device=self.device,
            disable_update=True,  # 添加在这里，禁用更新检查
        )
        return model

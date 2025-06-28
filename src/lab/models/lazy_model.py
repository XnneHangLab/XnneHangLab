from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lab._dataclass import RunnerSettings
from lab.config_manager.config import load_settings_file
from lab.utils.FFmpegHelper import get_audio_duration

if TYPE_CHECKING:
    from pathlib import Path

    from funasr import AutoModel

    from lab._typing import ASRResponse, VadResponse


class FunASRModel:
    # 这个 lazy-import 版本用在 gui 中可以提高操作的响应性, 以及提高初次加载界面时的加载速度
    # 但是它用在 cli 中显得不合理, 比如如果一个组合命令, 它需要同时用到 asr_and_vad 和 only_punc, 那么它就会多次 import Funasr, 每次在我电脑没插电的时候都需要 4~5s, 相当炸裂.
    # 所以我还需要一个 Non-Lazy import 版本的. 参见 model.py
    # 而把模型调用放在这里的原因是, 如果我不初始化模型, 那么这个文件的导入就是极快的
    def __init__(self):
        self.settings = load_settings_file("global.toml", RunnerSettings)
        self.base_model: str = str(self.settings.base_model)
        self.vad_model: str = str(self.settings.vad_model)
        self.punc_model: str = str(self.settings.punc_model)
        self.sense_voice_model: str = str(self.settings.sense_voice_model)
        self.device: str = self.settings.device

    def sense_voice(self):
        # Lazy-import
        from funasr import AutoModel

        model = AutoModel(
            model=self.settings.sense_voice_model,
            vad_model=self.settings.vad_model,  # vad 是用于音频分段的
            vad_kwargs={"max_single_segment_time": 30000},
            device=self.device,
            disable_update=True,
        )
        return model

    def vad_and_asr(self):
        # Lazy-import
        from funasr import AutoModel

        model = AutoModel(
            model=self.base_model,  # base
            vad_model=self.vad_model,  # 检测语音活动，自动分隔
            device=self.device,
            disable_update=True,  # 添加在这里，禁用更新检查
        )
        return model

    def only_txt(self):
        # Lazy-import
        from funasr import AutoModel

        model = AutoModel(model=self.base_model, device=self.device, disable_update=True)  # 也可以添加在这里
        return model

    def only_puc(self):
        # Lazy-import
        from funasr import AutoModel

        model = AutoModel(model=self.punc_model, device=self.device, disable_update=True)  # 也可以添加在这里
        return model

    def only_vad(self):
        # Lazy-import
        from funasr import AutoModel

        model = AutoModel(
            model=self.vad_model,
            device=self.device,
            disable_update=True,  # 添加在这里，禁用更新检查
        )
        return model


def generate_asr_results(model: AutoModel, input_path: Path) -> ASRResponse:
    # asr_and_vad 使用
    # input: Path("./bug/bug_0_30.opus")
    # return:
    # [{'key': 'bug_0_30',
    # 'text': '嗯 嗯  well come to the hollywood reporter actress round',
    # 'timestamp': [[12590, 12830], [16460, 16700], [27950, 28170], [28170, 28290], [28290, 28390], [28390, 28470], [28470, 28890], [28890, 29290], [29290, 29690], [29690, 30000]]}]

    settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)
    batch_size_s = settings.batch_size_s
    hot_word_path = settings.hot_words_path
    # 原本 AutoModel 支持 input_path 是 list 的情况，但这里我忽略了它，我只需要写一个BasicRunner，多任务自己处理。
    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} not found.")
    else:
        res: list[dict[str, Any]] = model.generate(  # type: ignore
            input=str(input_path),
            batch_size_s=batch_size_s,
            hot_word=str(hot_word_path),
        )
    if not res:
        raise ValueError("The res from automodel is empty.")
    res: dict[str, Any] = res[0]  # type: ignore
    response: ASRResponse = {
        "key": res.get("key", ""),
        "text": res.get("text", ""),
        "timestamp": res.get("timestamp", []),
    }
    return response


def generate_punc_results(model: AutoModel, input_text: str) -> str:
    # punc_model 使用
    # 参考: https://modelscope.cn/models/iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch/summary
    # input_text: 那今天的会就到这里吧 happy new year 明年见
    # return: 那今天的会就到这里吧，happy new year明年见。
    res = model.generate(input=input_text)  # type:ignore
    return res[0]["text"]  # type:ignore


def generate_vad_results(model: AutoModel, input_path: Path) -> VadResponse:
    res = model.generate(input=str(input_path))  # type:ignore
    # res: [{'key': 'bug_0_30', 'value': [[0, 3000], [3200, 4500]]}]
    audio_length: int = get_audio_duration(input_path)  # 获取音频长度
    response: VadResponse = {
        "key": res[0].get("key", ""),  # type:ignore
        "timestamp": res[0].get("value", []),  # type:ignore
        "audio_length": audio_length,
    }
    return response


def generate_sense_voice_results(model: AutoModel, input_path: Path, use_itn: bool = False) -> ASRResponse:
    # TODO https://github.com/FunAudioLLM/SenseVoice/issues/204
    # TODO https://github.com/FunAudioLLM/SenseVoice/issues/205
    # 在这些结束后，可以考虑把 text 拆分成 status,text.
    # 目前先返回 full_text
    settings: RunnerSettings = load_settings_file("global.toml", RunnerSettings)
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")
    res: list[dict[str, Any]] = model.generate(  # type: ignore
        input=str(input_path),  # 1分钟以上长音频
        cache={},
        language="auto",  # "zn", "en", "yue", "ja", "ko", "nospeech"
        use_itn=use_itn,
        batch_size_s=settings.batch_size_s,
        output_timestamp=True,  # 修复前 当同时开启vad和输出时间戳时model.py中会报错
    )
    if not res:
        raise ValueError("The res from automodel is empty.")
    res: dict[str, Any] = res[0]  # type: ignore
    response: ASRResponse = {
        "key": res.get("key", ""),
        "text": res.get("text", ""),
        "timestamp": res.get("timestamp", []),
    }
    return response

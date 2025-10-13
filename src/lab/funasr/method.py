from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.utils.FFmpegHelper import get_audio_duration

if TYPE_CHECKING:
    from pathlib import Path

    from funasr import AutoModel

    from lab._typing import ASRResponse, VadResponse


def generate_asr_results(model: AutoModel, input_path: Path) -> ASRResponse:
    # asr_and_vad 使用
    # input: Path("./bug/bug_0_30.opus")
    # return:
    # [{'key': 'bug_0_30',
    # 'text': '嗯 嗯  well come to the hollywood reporter actress round',
    # 'timestamp': [[12590, 12830], [16460, 16700], [27950, 28170], [28170, 28290], [28290, 28390], [28390, 28470], [28470, 28890], [28890, 29290], [29290, 29690], [29690, 30000]]}]

    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    batch_size_s = lab_settings.asr.funasr.batch_size_s
    hot_word_path = lab_settings.asr.funasr.hot_words_path
    # 原本 AutoModel 支持 input_path 是 list 的情况，但这里我忽略了它，我只需要写一个asr，多任务自己处理。
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
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")
    res: list[dict[str, Any]] = model.generate(  # type: ignore
        input=str(input_path),  # 1分钟以上长音频
        cache={},
        language="auto",  # "zn", "en", "yue", "ja", "ko", "nospeech"
        use_itn=use_itn,
        batch_size_s=lab_settings.asr.funasr.batch_size_s,
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

"""把英文的 title 以及选项转为中文
用户选择的是中文，实际上对应的是英文 or 数字
"""

from __future__ import annotations

from typing import TypedDict


class i18nDictionary(TypedDict):
    # guide
    open: tuple[str, int]
    close: tuple[str, int]

    # include_timestamp
    with_timestamp: tuple[str, int]
    without_timestamp: tuple[str, int]

    # subtitle_speed
    slow: tuple[str, int]
    normal: tuple[str, int]
    fast: tuple[str, int]

    # asr_model_provider
    funasr: tuple[str, int]
    whisper: tuple[str, int]

    # Device
    cpu: tuple[str, int]
    cuda: tuple[str, int]

    # whisper model size
    tiny: tuple[str, int]
    large_v3_turbo: tuple[str, int]


i18n_dictionary: i18nDictionary = {
    "open": ("开启", 0),
    "close": ("关闭", 1),
    "with_timestamp": ("带时间戳", 0),
    "without_timestamp": ("不带时间戳", 1),
    "slow": ("慢", 0),
    "normal": ("正常", 1),
    "fast": ("快", 2),
    "funasr": ("FunASR", 0),
    "whisper": ("Whisper", 1),
    "cpu": ("cpu", 0),
    "cuda": ("gpu", 1),
    "tiny": ("tiny", 0),
    "large_v3_turbo": ("large_v3_turbo", 1),
}

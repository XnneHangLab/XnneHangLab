"""把英文的 title 以及选项转为中文
用户选择的是中文，实际上对应的是英文 or 数字
"""

from __future__ import annotations

from typing import TypedDict


class AudioSettingDictionary(TypedDict):
    # guide
    open: tuple[str, int]
    close: tuple[str, int]

    # output_type
    with_timestamp: tuple[str, int]
    without_timestamp: tuple[str, int]

    # subtitle_speed
    slow: tuple[str, int]
    normal: tuple[str, int]
    fast: tuple[str, int]


audio_setting_dictionary: AudioSettingDictionary = {
    "open": ("开启", 0),
    "close": ("关闭", 1),
    "with_timestamp": ("带时间戳", 0),
    "without_timestamp": ("不带时间戳", 1),
    "slow": ("慢", 0),
    "normal": ("正常", 1),
    "fast": ("快", 2),
}

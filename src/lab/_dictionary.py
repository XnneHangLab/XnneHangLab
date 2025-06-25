"""把英文的 title 以及选项转为中文
用户选择的是中文，实际上对应的是英文 or 数字
"""

from __future__ import annotations

from typing import TypedDict


class AudioSettingDictionary(TypedDict):
    # guide
    open: tuple[int, str]
    close: tuple[int, str]

    # output_type
    with_timestamp: tuple[int, str]
    without_timestamp: tuple[int, str]

    # subtitle_speed
    slow: tuple[int, str]
    normal: tuple[int, str]
    fast: tuple[int, str]


audio_setting_dictionary: AudioSettingDictionary = {
    "open": (0, "开启"),
    "close": (1, "关闭"),
    "with_timestamp": (0, "带时间戳"),
    "without_timestamp": (1, "不带时间戳"),
    "slow": (0, "慢"),
    "normal": (1, "正常"),
    "fast": (2, "快"),
}


class VideoSettingDictionary(TypedDict):
    # guide
    open: tuple[int, str]
    close: tuple[int, str]

    # output_type
    with_timestamp: tuple[int, str]
    without_timestamp: tuple[int, str]

    # subtitle_speed
    slow: tuple[int, str]
    normal: tuple[int, str]
    fast: tuple[int, str]


video_setting_dictionary: VideoSettingDictionary = {
    "open": (0, "开启"),
    "close": (1, "关闭"),
    "with_timestamp": (0, "带时间戳"),
    "without_timestamp": (1, "不带时间戳"),
    "slow": (0, "慢"),
    "normal": (1, "正常"),
    "fast": (2, "快"),
}

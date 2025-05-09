from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab._typing import AudioSessionStateKeys, HomeSessionStateKeys, SettingSessionSateKeys

# 用于自动补全，防止输错 keys 导致的未初始化（这点真的挺ex的）
audio_keys: AudioSessionStateKeys = {
    "audio_name": "audio_name",
    "audio_file": "audio_file",
    "use_upload": "use_upload",
    "use_example": "use_example",
    "use_bilibili": "use_bilibili",
    "response_with_timestamp": "response_with_timestamp",
    "text_result": "text_result",
    "preview_srt_file": "preview_srt_file",
    "guide": "guide",
    "readme": "readme",
    "welcome": "welcome",
    "save": "save",
    "upload": "upload",
    "cut_line": "cut_line",
    "output_type": "output_type",
    "combine_line": "combine_line",
    "subtitle_speed": "subtitle_speed",
    "max_sentence_length": "max_sentence_length",
}

setting_keys: SettingSessionSateKeys = {
    "batch_size_s": "batch_size_s",
    "device": "device",
    "custom_output_dir": "custom_output_dir",
    "base_model": "base_model",
    "punc_model": "punc_model",
    "vad_model": "vad_model",
    "hot_words_path": "hot_words_path",
    "cache_dir": "cache_dir",
    "output_dir": "output_dir",
    "ffmpeg_path": "ffmpeg_path",
    "initial_settings": "initial_settings",
}


home_keys: HomeSessionStateKeys = {
    "stars": "stars",
}

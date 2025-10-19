"""Streamlit 用到的全局变量对应的 key
Streamlit 的全局变量存储于 st.session_state[key] 中，不具备自动补全功能，如果字母敲错了，可能导致变量未定义或者传参错误。
利用 TypedDict 的特性来存储这些 key, 在使用的时候可以自动补全。

st.session_state[typed_keys["keyname"]]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab._typing import AudioSessionStateKeys, HomeSessionStateKeys, SessionKeys, SettingSessionSateKeys

session_keys: SessionKeys = {"short_term_memory": "short_term_memory", "text_response": "text_response"}

# 用于自动补全，防止输错 keys 导致的未初始化（这点真的挺ex的）
audio_keys: AudioSessionStateKeys = {
    "audio_name": "audio_name",
    "audio_file": "audio_file",
    "use_upload": "use_upload",
    "use_example": "use_example",
    "use_bilibili": "use_bilibili",
    "sentences": "sentences",
    "text_result": "text_result",
    "preview_srt_file": "preview_srt_file",
    "guide": "guide",
    "readme": "readme",
    "welcome": "welcome",
    "save": "save",
    "upload": "upload",
    "cut_line": "cut_line",
    "include_timestamp": "include_timestamp",
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
    "whisper_models_base_dir": "whisper_models_base_dir",
    "whisper_model_size": "whisper_model_size",
    "asr_model_provider": "asr_model_provider",
}


home_keys: HomeSessionStateKeys = {
    "stars": "stars",
}

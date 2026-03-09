"""Streamlit session_state key 常量。

用法：
    from lab.streamlit.session_keys import audio_keys, setting_keys, home_keys, session_keys
    st.session_state[audio_keys["audio_file"]]
"""

from __future__ import annotations

from typing import TypedDict


class SessionKeys(TypedDict):
    short_term_memory: str
    text_response: str


class AudioSessionStateKeys(TypedDict):
    audio_name: str
    audio_file: str
    use_upload: str
    use_example: str
    use_bilibili: str
    sentences: str
    text_result: str
    preview_srt_file: str
    guide: str
    readme: str
    welcome: str
    save: str
    upload: str
    cut_line: str
    combine_line: str
    subtitle_speed: str
    max_sentence_length: str
    asr_model_provider: str
    whisper_model_size: str


class SettingSessionStateKeys(TypedDict):
    batch_size_s: str
    device: str
    custom_output_dir: str
    base_model: str
    punc_model: str
    vad_model: str
    hot_words_path: str
    cache_dir: str
    output_dir: str
    ffmpeg_path: str
    initial_settings: str
    whisper_models_base_dir: str
    whisper_model_size: str
    asr_model_provider: str


class HomeSessionStateKeys(TypedDict):
    stars: str


session_keys: SessionKeys = {
    "short_term_memory": "short_term_memory",
    "text_response": "text_response",
}

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
    "combine_line": "combine_line",
    "subtitle_speed": "subtitle_speed",
    "max_sentence_length": "max_sentence_length",
    "asr_model_provider": "asr_model_provider",
    "whisper_model_size": "whisper_model_size",
}

setting_keys: SettingSessionStateKeys = {
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

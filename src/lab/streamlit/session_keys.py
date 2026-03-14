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


class SettingSessionStateKeys(TypedDict):
    num_threads: str
    device: str
    custom_output_dir: str
    asr_model_dir: str
    vad_model_path: str
    cache_dir: str
    output_dir: str
    ffmpeg_path: str
    initial_settings: str
    qwen_model_id: str
    qwen_device: str
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
}

setting_keys: SettingSessionStateKeys = {
    "num_threads": "num_threads",
    "device": "device",
    "custom_output_dir": "custom_output_dir",
    "asr_model_dir": "asr_model_dir",
    "vad_model_path": "vad_model_path",
    "cache_dir": "cache_dir",
    "output_dir": "output_dir",
    "ffmpeg_path": "ffmpeg_path",
    "initial_settings": "initial_settings",
    "qwen_model_id": "qwen_model_id",
    "qwen_device": "qwen_device",
    "asr_model_provider": "asr_model_provider",
}

home_keys: HomeSessionStateKeys = {
    "stars": "stars",
}

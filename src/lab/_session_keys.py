from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab._typing import AudioSessionStateKeys

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

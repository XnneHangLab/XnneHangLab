from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from lab.config_manager.i18n import Guide, SubtitleSpeed

# 开放的配置项
AudioRecognizeSettingsTitle = Literal[
    "guide",
    "subtitle_speed",
]


class AudioRecognizeSettings(BaseModel):
    guide: Annotated[str, Field("open", title="指引")]
    subtitle_speed: Annotated[str, Field("normal", title="字幕速度")]

    _I18N_FIELDS = {
        "guide": Guide,
        "subtitle_speed": SubtitleSpeed,
    }

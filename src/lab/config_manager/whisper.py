from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from lab.config_manager.webui_i18n_model import Device, WebUIi18nSettings

# 并不是所有的配置项目都向用户开放。有 title 的是开放项。
# 开放的配置项
WhisperSettingsTitle = Literal["whisper_model_path", "device"]
# 下拉式配置项
WhisperSelectionSetting = Literal["device", "whisper_model_size"]
WhisperModelSize = Literal["whisper-tiny", "whisper-large-v3-turbo"]


class WhisperSettings(WebUIi18nSettings):
    whisper_models_base_dir: Annotated[str, Field("./models/whisper/", title="Whisper 模型存放列表目录")]
    whisper_model_size: Annotated[str, Field("whisper-large-v3-turbo", title="Whisper 模型规格")]
    device: Annotated[Device, Field("cuda", title="设备")]

    _FIELD_TO_LITERAL = {
        "device": Device,
        "whisper_model_size": WhisperSelectionSetting,
    }


def main():
    # 恢复默认配置
    from lab.config_manager.config import (
        XnneHangLabSettings,
        load_settings_file,
        search_for_settings_file,
        write_settings_file,
    )

    whisper_path = search_for_settings_file("whisper.toml")
    if whisper_path is not None and whisper_path.exists():
        whisper_path.unlink()  # ensure load default
    whisper_settings = load_settings_file("whisper.toml", WhisperSettings)
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    lab_settings.whisper = whisper_settings
    write_settings_file("lab.toml", lab_settings)
    funasr_path = search_for_settings_file("funasr.toml")
    if funasr_path is not None and funasr_path.exists():
        funasr_path.unlink()

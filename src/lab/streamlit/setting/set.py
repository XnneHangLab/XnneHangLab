from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import streamlit as st

from lab.api.clients import ReloadClient
from lab.config_manager import (
    ASRSettings,
    SherpaASRSettings,
    WhisperSettings,
    XnneHangLabSettings,
    get_setting_title,
    load_settings_file,
    write_settings_file,
)
from lab.streamlit.session_keys import setting_keys
from lab.streamlit.style import style

style()


@st.dialog("消息")
def message_box(title: str, message: str) -> None:
    """显示简单消息弹窗。

    Args:
        title: 弹窗标题。
        message: 弹窗正文。

    Returns:
        None.

    Raises:
        None.
    """
    st.markdown("")
    st.markdown(f"### {title} \n {message}")


def check_device_is_available(device: str) -> bool:
    """检查设备配置是否可用。

    Args:
        device: 待检查的设备名称。

    Returns:
        bool: 当前始终返回 True，作为占位实现。

    Raises:
        None.
    """
    if device == "cuda":
        pass
    return True


lab_settings = load_settings_file("lab.toml", setting=XnneHangLabSettings)
asr_settings: ASRSettings = lab_settings.asr
sherpa_settings: SherpaASRSettings = asr_settings.sherpa
whisper_settings: WhisperSettings = asr_settings.whisper


class BasicSettingsDict(TypedDict):
    device: str
    custom_output_dir: bool
    cache_dir: str
    output_dir: str
    ffmpeg_path: str
    asr_model_provider: str


class SherpaSettingsDict(TypedDict):
    asr_model_dir: str
    vad_model_path: str
    num_threads: int


class WhisperSettingsDict(TypedDict):
    whisper_models_base_dir: str
    whisper_model_size: str


class GlobalSettings(TypedDict):
    basic: BasicSettingsDict
    sherpa: SherpaSettingsDict
    whisper: WhisperSettingsDict


if setting_keys["initial_settings"] not in st.session_state:
    st.session_state.initial_settings = GlobalSettings(
        basic=BasicSettingsDict(
            device=asr_settings.device,
            custom_output_dir=asr_settings.custom_output_dir,
            cache_dir=asr_settings.cache_dir,
            output_dir=asr_settings.output_dir,
            ffmpeg_path=asr_settings.FFMPEG_PATH,
            asr_model_provider=asr_settings.asr_model_provider,
        ),
        sherpa=SherpaSettingsDict(
            asr_model_dir=sherpa_settings.asr_model_dir,
            vad_model_path=sherpa_settings.vad_model_path,
            num_threads=sherpa_settings.num_threads,
        ),
        whisper=WhisperSettingsDict(
            whisper_models_base_dir=whisper_settings.whisper_models_base_dir,
            whisper_model_size=whisper_settings.whisper_model_size,
        ),
    )


device = st.session_state.get(setting_keys["device"], asr_settings.device)
ffmpeg_path = st.session_state.get(setting_keys["ffmpeg_path"], asr_settings.FFMPEG_PATH)
cache_dir = st.session_state.get(setting_keys["cache_dir"], asr_settings.cache_dir)
custom_output_dir = st.session_state.get(setting_keys["custom_output_dir"], asr_settings.custom_output_dir)
output_dir = st.session_state.get(setting_keys["output_dir"], asr_settings.output_dir)
asr_model_provider = st.session_state.get(setting_keys["asr_model_provider"], asr_settings.asr_model_provider)

asr_model_dir = st.session_state.get(setting_keys["base_model"], sherpa_settings.asr_model_dir)
vad_model_path = st.session_state.get(setting_keys["vad_model"], sherpa_settings.vad_model_path)
num_threads = st.session_state.get(setting_keys["batch_size_s"], sherpa_settings.num_threads)

whisper_models_base_dir = st.session_state.get(
    setting_keys["whisper_models_base_dir"], whisper_settings.whisper_models_base_dir
)
whisper_model_size = st.session_state.get(setting_keys["whisper_model_size"], whisper_settings.whisper_model_size)

BOTSave = st.container()
BOTSetting = st.container(border=True)
with BOTSetting:
    st.markdown("")
    st.markdown("###### 基础配置")
    st.markdown("")
    device = st.selectbox(
        "设备选择",
        asr_settings.get_labels("device"),
        index=asr_settings.get_index("device"),
        key="device",
    )
    ffmpeg_path = st.text_input(
        get_setting_title("FFMPEG_PATH", ASRSettings),
        value=ffmpeg_path,
        placeholder="FFMPEG Path",
        key="ffmpeg_path",
    )
    asr_model_provider = st.selectbox(
        get_setting_title("asr_model_provider", ASRSettings),
        asr_settings.get_labels("asr_model_provider"),
        index=asr_settings.get_index("asr_model_provider"),
    )
    st.caption("Sherpa-ONNX 更适合中文字级时间戳，Whisper 更适合多语种识别。")
    if st.toggle("自定义输出目录", custom_output_dir, key="custom_output_dir"):
        output_dir = st.text_input(
            get_setting_title("output_dir", ASRSettings),
            value=output_dir,
            placeholder="Output Directory",
            key="output_dir",
        )
        cache_dir = st.text_input(
            get_setting_title("cache_dir", ASRSettings),
            value=cache_dir,
            placeholder="Cache Directory",
            key="cache_dir",
        )
    st.caption("默认输出目录与输入文件相邻；启用后会写入指定目录下的 `audio/` 与 `video/`。")
    st.markdown("")

    st.markdown("###### Sherpa-ONNX 配置")
    st.caption("所有路径均相对于当前工作目录。")
    asr_model_dir = st.text_input(
        get_setting_title("asr_model_dir", SherpaASRSettings),
        value=asr_model_dir,
        placeholder="ASR Model Directory",
        key="base_model",
    )
    vad_model_path = st.text_input(
        get_setting_title("vad_model_path", SherpaASRSettings),
        value=vad_model_path,
        placeholder="VAD Model Path",
        key="vad_model",
    )
    num_threads = st.number_input(
        get_setting_title("num_threads", SherpaASRSettings),
        value=num_threads,
        min_value=1,
        step=1,
        key="batch_size_s",
    )

    st.markdown("###### Whisper 配置")
    whisper_models_base_dir = st.text_input(
        get_setting_title("whisper_models_base_dir", WhisperSettings),
        value=whisper_models_base_dir,
        placeholder="Whisper Models Base Directory",
        key="whisper_models_base_dir",
    )
    whisper_model_size = st.selectbox(
        get_setting_title("whisper_model_size", WhisperSettings),
        whisper_settings.get_labels("whisper_model_size"),
        index=whisper_settings.get_index("whisper_model_size"),
        key="whisper_model_size",
    )
    st.caption("请确保 Whisper 模型目录下存在与所选规格对应的模型文件夹，例如 `whisper_models_base_dir/turbo`。")
    st.markdown("")

with BOTSave:
    col1, col2 = st.columns([0.75, 0.25])
    with col2:
        st.markdown("")
        st.markdown("")
        if st.button("**保存更改**", type="primary", use_container_width=True):
            initial_settings: GlobalSettings = st.session_state[setting_keys["initial_settings"]]
            current_settings: GlobalSettings = GlobalSettings(
                basic=BasicSettingsDict(
                    device=device,
                    custom_output_dir=custom_output_dir,
                    ffmpeg_path=ffmpeg_path or initial_settings["basic"]["ffmpeg_path"],
                    cache_dir=cache_dir or initial_settings["basic"]["cache_dir"],
                    output_dir=output_dir or initial_settings["basic"]["output_dir"],
                    asr_model_provider=asr_model_provider,
                ),
                sherpa=SherpaSettingsDict(
                    asr_model_dir=asr_model_dir or initial_settings["sherpa"]["asr_model_dir"],
                    vad_model_path=vad_model_path or initial_settings["sherpa"]["vad_model_path"],
                    num_threads=num_threads,
                ),
                whisper=WhisperSettingsDict(
                    whisper_models_base_dir=whisper_models_base_dir
                    or initial_settings["whisper"]["whisper_models_base_dir"],
                    whisper_model_size=whisper_model_size,
                ),
            )

            if current_settings != initial_settings:
                asr_settings.set_by_label("device", device)
                asr_settings.custom_output_dir = custom_output_dir or initial_settings["basic"]["custom_output_dir"]
                asr_settings.FFMPEG_PATH = ffmpeg_path or initial_settings["basic"]["ffmpeg_path"]
                asr_settings.cache_dir = cache_dir or initial_settings["basic"]["cache_dir"]
                asr_settings.output_dir = output_dir or initial_settings["basic"]["output_dir"]
                asr_settings.set_by_label("asr_model_provider", asr_model_provider)

                sherpa_settings.asr_model_dir = asr_model_dir or initial_settings["sherpa"]["asr_model_dir"]
                sherpa_settings.vad_model_path = vad_model_path or initial_settings["sherpa"]["vad_model_path"]
                sherpa_settings.num_threads = num_threads

                whisper_settings.whisper_models_base_dir = (
                    whisper_models_base_dir or initial_settings["whisper"]["whisper_models_base_dir"]
                )
                whisper_settings.whisper_model_size = (
                    whisper_model_size or initial_settings["whisper"]["whisper_model_size"]
                )

                asr_settings.sherpa = sherpa_settings
                asr_settings.whisper = whisper_settings
                lab_settings.asr = asr_settings

                write_settings_file(settings_name="lab.toml", settings=lab_settings)
                if (
                    current_settings["basic"]["device"] != initial_settings["basic"]["device"]
                    or current_settings["basic"]["asr_model_provider"]
                    != initial_settings["basic"]["asr_model_provider"]
                    or current_settings["sherpa"]["asr_model_dir"] != initial_settings["sherpa"]["asr_model_dir"]
                    or current_settings["sherpa"]["vad_model_path"] != initial_settings["sherpa"]["vad_model_path"]
                    or current_settings["sherpa"]["num_threads"] != initial_settings["sherpa"]["num_threads"]
                    or current_settings["whisper"]["whisper_model_size"]
                    != initial_settings["whisper"]["whisper_model_size"]
                ):
                    reload_client = ReloadClient("asr")
                    st.toast("正在重新加载模型，请稍候...")
                    reload_client.post()

                st.session_state[setting_keys["initial_settings"]] = current_settings
                message_box("保存成功", "你也可以直接修改 `config/lab.toml` 来调整配置。")
            else:
                message_box("未检测到更改", "配置未发生变化，无需保存。")

        if st.button("**恢复默认设置**", type="secondary", use_container_width=True):
            asr_setting_path = Path("config") / "asr.toml"
            if asr_setting_path.exists():
                asr_setting_path.unlink()
            asr_settings = load_settings_file("asr.toml", ASRSettings)
            lab_settings.asr = asr_settings
            asr_setting_path.unlink()
            write_settings_file("lab.toml", lab_settings)
            reload_client = ReloadClient("asr")
            st.toast("正在重新加载模型，请稍候...")
            reload_client.post()
            message_box("恢复成功", "配置已恢复为默认设置，刷新页面即可查看更改。")

    with col1:
        st.markdown("")
        st.markdown("")
        st.markdown("### 设置")
        st.caption("Settings")
        st.markdown("")

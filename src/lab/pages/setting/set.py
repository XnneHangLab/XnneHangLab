from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import streamlit as st

from lab._session_keys import setting_keys
from lab.api.clients import ReloadClient
from lab.config_manager import (
    ASRSettings,
    Device,
    FunASRSettings,
    WhisperSettings,
    XnneHangLabSettings,
    get_setting_title,
    load_settings_file,
    write_settings_file,
)
from lab.styles.global_style import style

# 我也很想用 st.write , 但是它存在类型未知 (> _ <)

style()


@st.dialog("消息")
def message_box(title: str, message: str):
    st.markdown("")
    st.markdown(f"### {title} \n {message}")


def check_device_is_available(device: Device):
    if device == "cuda":
        pass
    # todo. 检查cuda是否可用
    return True  # Assume device is available for now, replace with actual check


lab_settings = load_settings_file("lab.toml", setting=XnneHangLabSettings)
asr_settings: ASRSettings = lab_settings.asr
funasr_settings: FunASRSettings = asr_settings.funasr
whisper_settings: WhisperSettings = asr_settings.whisper


class BasicSettingsDict(TypedDict):
    device: Device
    custom_output_dir: bool
    cache_dir: str
    output_dir: str
    ffmpeg_path: str


class FunASRSettingsDict(TypedDict):
    base_model: str | None
    punc_model: str | None
    vad_model: str | None
    hot_words_path: str | None
    batch_size_s: int


class WhisperSettingsDict(TypedDict):
    whisper_models_base_dir: str | None
    whisper_model_size: str


class GlobalSettings(TypedDict):
    basic: BasicSettingsDict
    funasr: FunASRSettingsDict
    whisper: WhisperSettingsDict


# Store initial settings in session state if not already present
if setting_keys["initial_settings"] not in st.session_state:
    st.session_state.initial_settings = GlobalSettings(
        basic=BasicSettingsDict(
            device=asr_settings.device,
            custom_output_dir=asr_settings.custom_output_dir,
            cache_dir=asr_settings.cache_dir,
            output_dir=asr_settings.output_dir,
            ffmpeg_path=asr_settings.FFMPEG_PATH,
        ),
        funasr=FunASRSettingsDict(
            base_model=funasr_settings.base_model,
            punc_model=funasr_settings.punc_model,
            vad_model=funasr_settings.vad_model,
            hot_words_path=funasr_settings.hot_words_path,
            batch_size_s=funasr_settings.batch_size_s,
        ),
        whisper=WhisperSettingsDict(
            whisper_models_base_dir=whisper_settings.whisper_models_base_dir,
            whisper_model_size=whisper_settings.whisper_model_size,
        ),
    )

# Initialize current values from settings or session state if available after rerun
device = st.session_state.get(setting_keys["device"], asr_settings.device)
ffmpeg_path = st.session_state.get(setting_keys["ffmpeg_path"], asr_settings.FFMPEG_PATH)
cache_dir = st.session_state.get(setting_keys["cache_dir"], asr_settings.cache_dir)
custom_output_dir = st.session_state.get(setting_keys["custom_output_dir"], asr_settings.custom_output_dir)
output_dir = st.session_state.get(setting_keys["output_dir"], asr_settings.output_dir)
asr_model_provider = st.session_state.get(setting_keys["asr_model_provider"], asr_settings.asr_model_provider)

batch_size_s = st.session_state.get(setting_keys["batch_size_s"], funasr_settings.batch_size_s)
base_model = st.session_state.get(setting_keys["base_model"], funasr_settings.base_model)
punc_model = st.session_state.get(setting_keys["punc_model"], funasr_settings.punc_model)
vad_model = st.session_state.get(setting_keys["vad_model"], funasr_settings.vad_model)
hot_words_path = st.session_state.get(setting_keys["hot_words_path"], funasr_settings.hot_words_path)

whisper_models_base_dir = st.session_state.get(
    setting_keys["whisper_models_base_dir"], whisper_settings.whisper_models_base_dir
)
whisper_model_size = st.session_state.get(setting_keys["whisper_model_size"], whisper_settings.whisper_model_size)
# 之所以大费周章是为了防止用户打错单词前后不一致导致 session_keys 未定义


BOTSave = st.container()
BOTSetting = st.container(border=True)
with BOTSetting:
    st.markdown("")
    st.markdown("###### 基础配置")
    st.markdown("")
    device = st.selectbox(
        "设备选择", asr_settings.get_zh_option_list("device"), index=asr_settings.get_index("device"), key="device"
    )  # Add key
    ffmpeg_path = st.text_input(
        get_setting_title("FFMPEG_PATH", ASRSettings),
        value=ffmpeg_path,
        placeholder="FFMPEG Path",
        key="ffmpeg_path",
    )  # Add key
    # ASR 模型系列
    asr_model_provider = st.selectbox(
        get_setting_title("asr_model_provider", ASRSettings),
        asr_settings.get_zh_option_list("asr_model_provider"),
        index=asr_settings.get_index("asr_model_provider"),
    )
    st.caption("FunASR 仅支持中英文(但支持单词级的时间戳调整), Whisper 支持多语言。")
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
    st.caption("默认输出目录和输入文件相同，自定义后将会输出到指定目录的`audio/`和`video/`下方。")
    st.markdown("")
    st.markdown("###### FunASR 配置")
    st.caption("所有路径都与你的运行程序的工作目录相对应")
    batch_size_s = st.number_input(
        get_setting_title("batch_size_s", FunASRSettings),
        value=batch_size_s,
        placeholder="Batch Size",
        key="batch_size_s",
    )  # Add key
    hot_words_path = st.text_input(
        get_setting_title("hot_words_path", FunASRSettings),
        value=hot_words_path,
        placeholder="Hot Words Path",
        key="hot_words_path",
    )  # Add key
    base_model = st.text_input(
        get_setting_title("base_model", FunASRSettings),
        value=base_model,
        placeholder="Base Model Path",
        key="base_model",
    )  # Add key
    vad_model = st.text_input(
        get_setting_title("vad_model", FunASRSettings),
        value=vad_model,
        placeholder="VAD Model Path",
        key="vad_model",
    )  # Add key
    punc_model = st.text_input(
        get_setting_title("punc_model", FunASRSettings),
        value=punc_model,
        placeholder="Punctuation Model Path",
        key="punc_model",
    )  # Add key
    st.markdown("###### Whisper 配置")
    whisper_models_base_dir = st.text_input(
        get_setting_title("whisper_models_base_dir", WhisperSettings),
        value=whisper_models_base_dir,
        placeholder="Whisper Models Base Directory",
        key="whisper_models_base_dir",
    )  # Add key
    whisper_model_size = st.selectbox(
        get_setting_title("whisper_model_size", WhisperSettings),
        whisper_settings.get_zh_option_list("whisper_model_size"),
        index=whisper_settings.get_index("whisper_model_size"),
        key="whisper_model_size",
    )  # Add key
    st.caption(
        "请确保下载的模型文件夹存放于 whisper_models_base_dir 下方且命名与选项，如 whisper_models_base_dir/large_v3_turbo"
    )

    st.markdown("")

with BOTSave:
    col1, col2 = st.columns([0.75, 0.25])
    with col2:
        st.markdown("")
        st.markdown("")
        if st.button("**保存更改**", type="primary", use_container_width=True):
            current_settings: GlobalSettings = GlobalSettings(
                basic=BasicSettingsDict(
                    device=device,  # type: ignore
                    custom_output_dir=custom_output_dir,
                    ffmpeg_path=ffmpeg_path,
                    cache_dir=cache_dir,
                    asr_model_provider=asr_model_provider,
                ),
                funasr=FunASRSettingsDict(
                    base_model=base_model,
                    punc_model=punc_model,
                    vad_model=vad_model,
                    hot_words_path=hot_words_path,
                    batch_size_s=batch_size_s,
                ),
                whisper=WhisperSettingsDict(
                    whisper_models_base_dir=whisper_models_base_dir,
                    whisper_model_size=whisper_model_size,
                ),
            )

            initial_settings = st.session_state[setting_keys["initial_settings"]]

            if current_settings != initial_settings:  # Compare dictionaries
                asr_settings.zh_set_value("device", device)
                asr_settings.custom_output_dir = (
                    custom_output_dir if custom_output_dir else initial_settings["basic"]["custom_output_dir"]
                )
                asr_settings.FFMPEG_PATH = ffmpeg_path if ffmpeg_path else initial_settings["paths"]["FFMPEG_PATH"]
                asr_settings.cache_dir = cache_dir if cache_dir else initial_settings["paths"]["cache_dir"]
                asr_settings.output_dir = output_dir if output_dir else initial_settings["paths"]["output_dir"]
                asr_settings.zh_set_value("asr_model_provider", asr_model_provider)  # type: ignore

                funasr_settings.batch_size_s = batch_size_s
                funasr_settings.base_model = base_model if base_model else initial_settings["paths"]["base_model"]
                funasr_settings.punc_model = punc_model if punc_model else initial_settings["paths"]["punc_model"]
                funasr_settings.vad_model = vad_model if vad_model else initial_settings["paths"]["vad_model"]
                funasr_settings.hot_words_path = (
                    hot_words_path if hot_words_path else initial_settings["paths"]["hot_words_path"]
                )

                whisper_settings.whisper_models_base_dir = (
                    whisper_models_base_dir
                    if whisper_models_base_dir
                    else initial_settings["paths"]["whisper_models_base_dir"]
                )
                whisper_settings.whisper_model_size = (
                    whisper_model_size if whisper_model_size else initial_settings["paths"]["whisper_model_size"]
                )

                asr_settings.whisper = whisper_settings
                asr_settings.funasr = funasr_settings
                lab_settings.asr = asr_settings

                write_settings_file(settings_name="lab.toml", settings=lab_settings)
                if (
                    current_settings["basic"]["device"] != initial_settings["basic"]["device"]
                    or current_settings["funasr"]["base_model"] != initial_settings["paths"]["base_model"]
                    or current_settings["funasr"]["punc_model"] != initial_settings["paths"]["punc_model"]
                    or current_settings["funasr"]["vad_model"] != initial_settings["paths"]["vad_model"]
                ):
                    # 需要重新加载模型
                    reload_client = ReloadClient("asr")
                    st.toast("正在重新加载模型，请稍候...")
                    reload_client.post()
                st.session_state[setting_keys["initial_settings"]] = (
                    current_settings  # Update initial settings after save
                )
                message_box("保存成功！", "你也可以通过手动配置 `funasr.toml` 来修改配置。")
            else:
                message_box("未检测到更改", "配置未发生任何变化，无需保存。")

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
            message_box("恢复成功！", "配置已恢复为默认设置。刷新页面即可查看更改。")

    with col1:
        st.markdown("")
        st.markdown("")
        st.markdown("### 设置")
        st.caption("Settings")
        st.markdown("")

from __future__ import annotations

from pathlib import Path

import streamlit as st

from lab._session_keys import setting_keys
from lab.api.clients import ReloadClient
from lab.config_manager import Device, FunASRSettings, get_setting_title, load_settings_file, write_settings_file
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


settings = load_settings_file("funasr.toml", setting=FunASRSettings)

# Store initial settings in session state if not already present
if setting_keys["initial_settings"] not in st.session_state:
    st.session_state.initial_settings = {
        "basic": {
            setting_keys["batch_size_s"]: settings.batch_size_s,
            setting_keys["device"]: settings.device,
            setting_keys["custom_output_dir"]: settings.custom_output_dir,
        },
        "paths": {
            setting_keys["base_model"]: settings.base_model,
            setting_keys["punc_model"]: settings.punc_model,
            setting_keys["vad_model"]: settings.vad_model,
            setting_keys["hot_words_path"]: settings.hot_words_path,
            setting_keys["ffmpeg_path"]: settings.FFMPEG_PATH,
            setting_keys["cache_dir"]: settings.cache_dir,
            setting_keys["output_dir"]: settings.output_dir,
        },
    }

# Initialize current values from settings or session state if available after rerun
batch_size_s = st.session_state.get(setting_keys["batch_size_s"], settings.batch_size_s)
device = st.session_state.get(setting_keys["device"], settings.device)
base_model = st.session_state.get(setting_keys["base_model"], settings.base_model)
punc_model = st.session_state.get(setting_keys["punc_model"], settings.punc_model)
vad_model = st.session_state.get(setting_keys["vad_model"], settings.vad_model)
hot_words_path = st.session_state.get(setting_keys["hot_words_path"], settings.hot_words_path)
ffmpeg_path = st.session_state.get(setting_keys["ffmpeg_path"], settings.FFMPEG_PATH)
cache_dir = st.session_state.get(setting_keys["cache_dir"], settings.cache_dir)
custom_output_dir = st.session_state.get(setting_keys["custom_output_dir"], settings.custom_output_dir)
output_dir = st.session_state.get(setting_keys["output_dir"], settings.output_dir)
# 之所以大费周章是为了防止用户打错单词前后不一致导致 session_keys 未定义


BOTSave = st.container()
BOTSetting = st.container(border=True)
with BOTSetting:
    st.markdown("")
    st.markdown("###### 基础配置")
    st.markdown("")
    batch_size_s = st.number_input(
        get_setting_title("batch_size_s", FunASRSettings),
        value=batch_size_s,
        placeholder="Batch Size",
        key="batch_size_s",
    )  # Add key
    device = st.selectbox("设备选择", ["cpu", "cuda"], index=0 if device == "cpu" else 1, key="device")  # Add key
    st.markdown("")
    st.markdown("###### 路径配置")
    st.caption("所有路径都与你的运行程序的工作目录相对应")
    hot_words_path = st.text_input(
        get_setting_title("hot_words_path", FunASRSettings),
        value=hot_words_path,
        placeholder="Hot Words Path",
        key="hot_words_path",
    )  # Add key
    ffmpeg_path = st.text_input(
        get_setting_title("FFMPEG_PATH", FunASRSettings),
        value=ffmpeg_path,
        placeholder="FFMPEG Path",
        key="ffmpeg_path",
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
    if st.toggle("自定义输出目录", custom_output_dir, key="custom_output_dir"):
        output_dir = st.text_input(
            get_setting_title("output_dir", FunASRSettings),
            value=output_dir,
            placeholder="Output Directory",
            key="output_dir",
        )
    st.caption("默认输出目录和输入文件相同，自定义后将会输出到指定目录的`audio/`和`video/`下方。")
    st.markdown("")

with BOTSave:
    col1, col2 = st.columns([0.75, 0.25])
    with col2:
        st.markdown("")
        st.markdown("")
        if st.button("**保存更改**", type="primary", use_container_width=True):
            current_settings = {
                "basic": {
                    "batch_size_s": batch_size_s,
                    "device": device,
                    "custom_output_dir": custom_output_dir,
                },
                "paths": {
                    "base_model": base_model,
                    "punc_model": punc_model,
                    "vad_model": vad_model,
                    "hot_words_path": hot_words_path,
                    "FFMPEG_PATH": ffmpeg_path,
                    "cache_dir": cache_dir,
                    "output_dir": output_dir,
                },
            }

            initial_settings = st.session_state[setting_keys["initial_settings"]]

            if current_settings != initial_settings:  # Compare dictionaries
                settings.batch_size_s = batch_size_s
                settings.device = device if check_device_is_available(device=device) else "cpu"  # type: ignore
                settings.custom_output_dir = (
                    custom_output_dir if custom_output_dir else initial_settings["basic"]["custom_output_dir"]
                )
                settings.base_model = base_model if base_model else initial_settings["paths"]["base_model"]
                settings.punc_model = punc_model if punc_model else initial_settings["paths"]["punc_model"]
                settings.vad_model = vad_model if vad_model else initial_settings["paths"]["vad_model"]
                settings.hot_words_path = (
                    hot_words_path if hot_words_path else initial_settings["paths"]["hot_words_path"]
                )
                settings.FFMPEG_PATH = ffmpeg_path if ffmpeg_path else initial_settings["paths"]["FFMPEG_PATH"]
                settings.cache_dir = cache_dir if cache_dir else initial_settings["paths"]["cache_dir"]
                settings.output_dir = output_dir if output_dir else initial_settings["paths"]["output_dir"]
                write_settings_file(settings_name="funasr.toml", settings=settings)
                if (
                    current_settings["basic"]["device"] != initial_settings["basic"]["device"]
                    or current_settings["paths"]["base_model"] != initial_settings["paths"]["base_model"]
                    or current_settings["paths"]["punc_model"] != initial_settings["paths"]["punc_model"]
                    or current_settings["paths"]["vad_model"] != initial_settings["paths"]["vad_model"]
                ):
                    # 需要重新加载模型
                    reload_client = ReloadClient("audio")
                    st.toast("正在重新加载模型，请稍候...")
                    reload_client.post()
                st.session_state[setting_keys["initial_settings"]] = (
                    current_settings  # Update initial settings after save
                )
                message_box("保存成功！", "你也可以通过手动配置 `funasr.toml` 来修改配置。")
            else:
                message_box("未检测到更改", "配置未发生任何变化，无需保存。")

        if st.button("**恢复默认设置**", type="secondary", use_container_width=True):
            settings = Path("config") / "funasr.toml"
            settings.unlink()
            load_settings_file("funasr.toml", FunASRSettings)
            message_box("恢复成功！", "配置已恢复为默认设置。刷新页面即可查看更改。")

    with col1:
        st.markdown("")
        st.markdown("")
        st.markdown("### 设置")
        st.caption("Settings")
        st.markdown("")

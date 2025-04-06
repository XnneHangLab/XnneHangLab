from __future__ import annotations

from pathlib import Path

import streamlit as st

from lab._dataclass import Device, RunnerSettings
from lab.styles.global_style import style
from lab.utils.config import get_setting_title, load_settings_file, write_settings_file

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


settings = load_settings_file("global.toml", setting=RunnerSettings)

# Store initial settings in session state if not already present
if "initial_settings" not in st.session_state:
    st.session_state.initial_settings = {
        "basic": {
            "batch_size_s": settings.batch_size_s,
            "device": settings.device,
            "custom_output_dir": settings.custom_output_dir,
        },
        "paths": {
            "base_model": settings.base_model,
            "punc_model": settings.punc_model,
            "vad_model": settings.vad_model,
            "hot_words_path": settings.hot_words_path,
            "FFMPEG_PATH": settings.FFMPEG_PATH,
            "cache_dir": settings.cache_dir,
            "output_dir": settings.output_dir,
        },
    }

# Initialize current values from settings or session state if available after rerun
batch_size_s = st.session_state.get("batch_size_s", settings.batch_size_s)
device = st.session_state.get("device", settings.device)
base_model = st.session_state.get("base_model", settings.base_model)
punc_model = st.session_state.get("punc_model", settings.punc_model)
vad_model = st.session_state.get("vad_model", settings.vad_model)
hot_words_path = st.session_state.get("hot_words_path", settings.hot_words_path)
ffmpeg_path = st.session_state.get("ffmpeg_path", settings.FFMPEG_PATH)
cache_dir = st.session_state.get("cache_dir", settings.cache_dir)
custom_output_dir = st.session_state.get("custom_output_dir", settings.custom_output_dir)
output_dir = st.session_state.get("output_dir", settings.output_dir)


BOTSave = st.container()
BOTSetting = st.container(border=True)
with BOTSetting:
    st.markdown("")
    st.markdown("###### 基础配置")
    st.markdown("")
    batch_size_s = st.number_input(
        get_setting_title("batch_size_s", RunnerSettings),
        value=batch_size_s,
        placeholder="Batch Size",
        key="batch_size_s",
    )  # Add key
    device = st.selectbox("设备选择", ["cpu", "cuda"], index=0 if device == "cpu" else 1, key="device")  # Add key
    st.markdown("")
    st.markdown("###### 路径配置")
    st.caption("所有路径都与你的运行程序的工作目录相对应")
    hot_words_path = st.text_input(
        get_setting_title("hot_words_path", RunnerSettings),
        value=hot_words_path,
        placeholder="Hot Words Path",
        key="hot_words_path",
    )  # Add key
    ffmpeg_path = st.text_input(
        get_setting_title("FFMPEG_PATH", RunnerSettings),
        value=ffmpeg_path,
        placeholder="FFMPEG Path",
        key="ffmpeg_path",
    )  # Add key
    base_model = st.text_input(
        get_setting_title("base_model", RunnerSettings),
        value=base_model,
        placeholder="Base Model Path",
        key="base_model",
    )  # Add key
    vad_model = st.text_input(
        get_setting_title("vad_model", RunnerSettings),
        value=vad_model,
        placeholder="VAD Model Path",
        key="vad_model",
    )  # Add key
    punc_model = st.text_input(
        get_setting_title("punc_model", RunnerSettings),
        value=punc_model,
        placeholder="Punctuation Model Path",
        key="punc_model",
    )  # Add key
    if st.toggle("自定义输出目录", custom_output_dir, key="custom_output_dir"):
        output_dir = st.text_input(
            get_setting_title("output_dir", RunnerSettings),
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

            initial_settings = st.session_state.initial_settings

            if current_settings != initial_settings:  # Compare dictionaries
                settings.batch_size_s = batch_size_s
                settings.device = device if check_device_is_available(device=device) else "cpu"  # type: ignore
                settings.custom_output_dir = custom_output_dir
                settings.base_model = base_model
                settings.punc_model = punc_model
                settings.vad_model = vad_model
                settings.hot_words_path = hot_words_path
                settings.FFMPEG_PATH = ffmpeg_path
                settings.cache_dir = cache_dir
                settings.output_dir = output_dir
                write_settings_file(settings_name="global.toml", settings=settings)
                message_box("保存成功！", "你也可以通过手动配置 `global.toml` 来修改配置。")
                st.session_state.save = True
                st.session_state.initial_settings = current_settings  # Update initial settings after save
            else:
                message_box("未检测到更改", "配置未发生任何变化，无需保存。")

        if st.button("**恢复默认设置**", type="secondary", use_container_width=True):
            settings = Path("config") / "global.toml"
            settings.unlink()
            load_settings_file("global.toml", RunnerSettings)
            message_box("恢复成功！", "配置已恢复为默认设置。刷新页面即可查看更改。")

    with col1:
        st.markdown("")
        st.markdown("")
        st.markdown("### 设置")
        st.caption("Settings")
        st.markdown("")

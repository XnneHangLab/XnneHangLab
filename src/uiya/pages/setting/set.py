import streamlit as st
from pathlib import Path
from uiya.styles.global_style import style
from uiya.utils.config import load_settings_file, write_settings_file
from uiya._typing import Device

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


settings = load_settings_file("acgo.toml")

# Store initial settings in session state if not already present
if "initial_settings" not in st.session_state:
    st.session_state.initial_settings = {
        "basic": {
            "batch_size_s": settings.basic.batch_size_s,
            "device": settings.basic.device,
            "punctuation_list": settings.basic.punctuation_list,
        },
        "paths": {
            "base_model": settings.paths.base_model,
            "punc_model": settings.paths.punc_model,
            "vad_model": settings.paths.vad_model,
            "hot_words_path": settings.paths.hot_words_path,
            "FFMPEG_PATH": settings.paths.FFMPEG_PATH,
        },
        "extra": {
            "cut": settings.extra.cut,
            "cut_line": settings.extra.cut_line,
            "combine": settings.extra.combine,
            "combine_line": settings.extra.combine_line,
            "max_sentence_length": settings.extra.max_sentence_length,
            "need_punc": settings.extra.need_punc,
        },
    }

# Initialize current values from settings or session state if available after rerun
batch_size_s = st.session_state.get("batch_size_s", settings.basic.batch_size_s)
device = st.session_state.get("device", settings.basic.device)
punctuation_list = st.session_state.get(
    "punctuation_list", settings.basic.punctuation_list
)
base_model = st.session_state.get("base_model", settings.paths.base_model)
punc_model = st.session_state.get("punc_model", settings.paths.punc_model)
vad_model = st.session_state.get("vad_model", settings.paths.vad_model)
hot_words_path = st.session_state.get("hot_words_path", settings.paths.hot_words_path)
ffmpeg_path = st.session_state.get("ffmpeg_path", settings.paths.FFMPEG_PATH)
cut = st.session_state.get("cut", settings.extra.cut)
cut_line = st.session_state.get("cut_line", settings.extra.cut_line)
combine = st.session_state.get("combine", settings.extra.combine)
combine_line = st.session_state.get("combine_line", settings.extra.combine_line)
max_sentence_length = st.session_state.get(
    "max_sentence_length", settings.extra.max_sentence_length
)
need_punc = st.session_state.get("need_punc", settings.extra.need_punc)


BOTSave = st.container()
BOTSetting = st.container(border=True)
with BOTSetting:
    st.markdown("")
    st.markdown("###### 基础配置")
    st.markdown("")
    batch_size_s = st.number_input(
        "批处理大小(默认300,只要能吃满显卡或者CPU即可)",
        value=batch_size_s,
        placeholder="Batch Size",
        key="batch_size_s",
    )  # Add key
    device = st.selectbox(
        "设备选择", ["cpu", "cuda"], index=0 if device == "cpu" else 1, key="device"
    )  # Add key
    punctuation_list = st.text_input(
        "标点符号列表",
        value=punctuation_list,
        placeholder="Punctuation List",
        key="punctuation_list",
    )  # Add key
    st.markdown("")
    st.markdown("###### 路径配置")
    st.caption("所有路径都与你的运行程序的工作目录相对应")
    hot_words_path = st.text_input(
        "热词路径",
        value=hot_words_path,
        placeholder="Hot Words Path",
        key="hot_words_path",
    )  # Add key
    ffmpeg_path = st.text_input(
        "FFMPEG 路径", value=ffmpeg_path, placeholder="FFMPEG Path", key="ffmpeg_path"
    )  # Add key
    base_model = st.text_input(
        "基础模型路径",
        value=base_model,
        placeholder="Base Model Path",
        key="base_model",
    )  # Add key
    vad_model = st.text_input(
        "VAD 模型路径", value=vad_model, placeholder="VAD Model Path", key="vad_model"
    )  # Add key
    punc_model = st.text_input(
        "标点模型路径",
        value=punc_model,
        placeholder="Punctuation Model Path",
        key="punc_model",
    )  # Add key
    st.markdown("")
    st.markdown("###### 字幕配置")
    cut = st.checkbox("是否切割字幕", value=cut, key="cut")  # Add key
    cut_line = st.number_input(
        "切割行数", value=cut_line, placeholder="Cut Line", key="cut_line"
    )  # Add key
    combine = st.checkbox("是否合并字幕", value=combine, key="combine")  # Add key
    combine_line = st.number_input(
        "合并行数", value=combine_line, placeholder="Combine Line", key="combine_line"
    )  # Add key
    max_sentence_length = st.number_input(
        "最大句子长度",
        value=max_sentence_length,
        placeholder="Max Sentence Length",
        key="max_sentence_length",
    )  # Add key
    need_punc = st.checkbox("是否需要标点", value=need_punc, key="need_punc")  # Add key
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
                    "punctuation_list": punctuation_list,
                },
                "paths": {
                    "base_model": base_model,
                    "punc_model": punc_model,
                    "vad_model": vad_model,
                    "hot_words_path": hot_words_path,
                    "FFMPEG_PATH": ffmpeg_path,
                },
                "extra": {
                    "cut": cut,
                    "cut_line": cut_line,
                    "combine": combine,
                    "combine_line": combine_line,
                    "max_sentence_length": max_sentence_length,
                    "need_punc": need_punc,
                },
            }

            initial_settings = st.session_state.initial_settings

            if current_settings != initial_settings:  # Compare dictionaries
                settings.basic.batch_size_s = batch_size_s
                settings.basic.device = device if check_device_is_available(device=device) else "cpu"  # type: ignore
                settings.basic.punctuation_list = punctuation_list
                settings.paths.base_model = base_model
                settings.paths.punc_model = punc_model
                settings.paths.vad_model = vad_model
                settings.paths.hot_words_path = hot_words_path
                settings.paths.FFMPEG_PATH = ffmpeg_path
                settings.extra.cut = cut
                settings.extra.cut_line = cut_line
                settings.extra.combine = combine
                settings.extra.combine_line = combine_line
                settings.extra.max_sentence_length = max_sentence_length
                settings.extra.need_punc = need_punc
                write_settings_file(settings_file=Path("acgo.yaml"), settings=settings)
                message_box(
                    "保存成功！", "你也可以通过手动配置 `acgo.yaml` 来修改配置。"
                )
                st.session_state.save = True
                st.session_state.initial_settings = (
                    current_settings  # Update initial settings after save
                )
            else:
                message_box("未检测到更改", "配置未发生任何变化，无需保存。")

    with col1:
        st.markdown("")
        st.markdown("")
        st.markdown("### 设置")
        st.caption("Settings")
        st.markdown("")

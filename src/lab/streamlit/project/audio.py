from __future__ import annotations

import datetime
import shutil
from pathlib import Path

import streamlit as st

from lab.api.clients import ASRClient, ASRRequest
from lab.asr.combiner import combine_sentences
from lab.asr.cutter import cut_sentences
from lab.config_manager import (
    ASRSettings,
    AudioRecognizeSettings,
    XnneHangLabSettings,
    get_setting_title,
    load_settings_file,
    write_settings_file,
)
from lab.logger.logger_group import logger
from lab.streamlit.dialogs.audio import AudioReadme, upload_audio
from lab.streamlit.session_keys import audio_keys
from lab.streamlit.style import style
from lab.utils.public import (
    parse_srt_file,
)
from lab.utils.SrtHelper import write_srt_from_sentences

_asr_logger = logger.bind(group="asr")

# TODO 以 sys.argv 的方式调用 basic_runner, 这里不再写入基础函数.
# ============== 0.加载配置，配置字体

style()
lab_settings: XnneHangLabSettings = load_settings_file("lab.toml", setting=XnneHangLabSettings)
asr_setting: ASRSettings = lab_settings.asr
webui_setting: AudioRecognizeSettings = lab_settings.webui

# ============== 1.初始化持久化参数

# 参数说明参见 _session_keys.py

guide = st.session_state.get(audio_keys["guide"], webui_setting.guide)
subtitle_speed = st.session_state.get(audio_keys["subtitle_speed"], webui_setting.subtitle_speed)
cut_line: int = st.session_state.get(audio_keys["cut_line"], asr_setting.cut_line)
combine_line: int = st.session_state.get(audio_keys["combine_line"], asr_setting.combine_line)
max_sentence_length: int = st.session_state.get(audio_keys["max_sentence_length"], asr_setting.max_sentence_length)
asr_model_provider = st.session_state.get(audio_keys["asr_model_provider"], asr_setting.asr_model_provider)
qwen_model_name = st.session_state.get(
    audio_keys["qwen_model_name"],
    (lab_settings.asr.qwen_asr.preload_models[0] if lab_settings.asr.qwen_asr.preload_models else "0.6b"),
)


# 用于音频上传
if audio_keys["audio_name"] not in st.session_state:
    st.session_state[audio_keys["audio_name"]] = None
if audio_keys["use_upload"] not in st.session_state:
    st.session_state[audio_keys["use_upload"]] = False
if audio_keys["use_example"] not in st.session_state:
    st.session_state[audio_keys["use_example"]] = False
if audio_keys["use_bilibili"] not in st.session_state:
    st.session_state[audio_keys["use_bilibili"]] = False
if audio_keys["audio_file"] not in st.session_state:
    st.session_state[audio_keys["audio_file"]] = None


# 用于音频识别
if audio_keys["sentences"] not in st.session_state:
    st.session_state[audio_keys["sentences"]] = None
if audio_keys["text_result"] not in st.session_state:
    st.session_state[audio_keys["text_result"]] = None

# 字幕预览
if audio_keys["preview_srt_file"] not in st.session_state:
    st.session_state[audio_keys["preview_srt_file"]] = None


# 用于消息提示
if audio_keys["readme"] not in st.session_state and webui_setting.guide == "open":
    AudioReadme()
    st.session_state[audio_keys["readme"]] = True
if audio_keys["welcome"] in st.session_state:
    st.toast("欢迎使用 ~", icon=":material/verified:")
    del st.session_state["welcome"]
if audio_keys["save"] in st.session_state:
    st.toast("参数已成功保存", icon=":material/verified:")
    del st.session_state["save"]
if audio_keys["upload"] in st.session_state:
    st.toast("文件上传成功！", icon=":material/verified:")
    del st.session_state["upload"]

# ============== 2.页面布局

working_tab, setting_tab = st.tabs(["**音频识别**", "**参数设置**"])


# 2.1. 配置
# 参数配置
with setting_tab:
    AudioSave = st.container()
    AudioSetting = st.container(border=True)

    with AudioSetting:
        guide = st.selectbox(
            get_setting_title("guide", AudioRecognizeSettings),
            webui_setting.get_labels("guide"),
            index=webui_setting.get_index("guide"),
        )
        asr_model_provider = st.selectbox(
            get_setting_title("asr_model_provider", ASRSettings),
            asr_setting.get_labels("asr_model_provider"),
            index=asr_setting.get_index("asr_model_provider"),
        )
        if asr_model_provider == "Qwen3-ASR":
            qwen_model_name = st.selectbox(
                "Qwen3-ASR 模型",
                options=["0.6b", "1.7b"],
                index=0 if qwen_model_name == "0.6b" else 1,
                key=audio_keys["qwen_model_name"],
            )
        st.caption("Qwen3-ASR is the default multilingual engine. Sherpa-ONNX stays as a lightweight fallback.")
    with AudioSave:
        col1, col2 = st.columns([0.75, 0.25])
        st.markdown("")
        with col2:
            st.markdown("")
            st.markdown("")
            if st.button("**保存更改**", use_container_width=True, type="primary"):
                webui_setting.set_by_label("guide", guide)
                asr_setting.set_by_label("asr_model_provider", asr_model_provider)
                lab_settings.asr = asr_setting
                lab_settings.webui = webui_setting
                write_settings_file("lab.toml", lab_settings)
                st.session_state[audio_keys["save"]] = True
                st.rerun()
        with col1:
            st.markdown("")
            st.markdown("")
            st.markdown("### 参数设置")
            st.caption("Changing Parameter Settings")

# 2.2. 识别页面
# 通过 ctrl + f 快速定位到需要的功能
# 2.2.1. 音轨预览
# 2.2.2. 字幕预览
# 2.2.3. 字幕工具
# 2.2.4. 上传文件
# 2.2.5. 开始识别
# 音频识别
with working_tab:
    # 配置处理
    col1, col2 = st.columns([0.75, 0.25])  # 置顶标题、执行按钮流程模块

    # 标题模块
    with col1:
        st.markdown("")
        st.markdown("")
        st.subheader("AI 全自动音频识别")
        st.caption("AI Automatic Audio Recognize")

    with col2:
        st.markdown("")
        st.markdown("")
        # 2.2.5. 开始识别
        # 开始识别
        if st.button("**开始识别**", type="primary", use_container_width=True):
            if st.session_state["audio_file"] is not None:
                audio_file = st.session_state[audio_keys["audio_file"]]
                print("\n" + "=" * 50)
                print("\n\033[1;39m*** XnneHangLab 音频识别 ***\033[0m")
                st.toast(
                    "任务开始执行！请勿在运行时切换菜单或修改参数!",
                    icon=":material/rocket_launch:",
                )

                msg_ved = st.toast("正在对音频进行预处理", icon=":material/graphic_eq:")
                current_time = datetime.datetime.now().strftime("_%Y%m%d%H%M%S")
                # 方式一: 使用上传的音频文件
                if st.session_state[audio_keys["use_upload"]]:
                    audio_first_name = audio_file.name.split(".")[0]
                    st.session_state[audio_keys["audio_name"]] = audio_file.name
                    cache_dir = Path(asr_setting.cache_dir) / audio_first_name / current_time
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    # TODO 这里只是复制到了 cache_Dir ,实际上， 我们需要把它处理成 wav.
                    with (cache_dir / st.session_state[audio_keys["audio_name"]]).open("wb") as file:
                        file.write(audio_file.getbuffer())

                # 方式二: 使用示例音频文件
                elif st.session_state[audio_keys["use_example"]]:
                    if st.session_state[audio_keys["audio_name"]]:
                        audio_first_name = st.session_state[audio_keys["audio_name"]].split(".")[0]
                    else:
                        st.toast("请先选择示例文件", icon=":material/error:")
                        st.stop()
                    cache_dir = Path(asr_setting.cache_dir) / audio_first_name / current_time
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(
                        Path(f"examples/{st.session_state[audio_keys['audio_name']]}"),
                        cache_dir / st.session_state[audio_keys["audio_name"]],
                    )

                # 方式三: 使用 b站视频下载模块
                elif st.session_state[audio_keys["use_bilibili"]]:
                    if st.session_state[audio_keys["audio_name"]]:
                        audio_first_name = st.session_state[audio_keys["audio_name"]].split(".")[0]
                    else:
                        st.toast("请先选择音频文件", icon=":material/error:")
                        st.stop()

                    cache_dir = Path(asr_setting.cache_dir) / audio_first_name / current_time
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(
                        Path(st.session_state[audio_keys["audio_file"]]),
                        cache_dir / st.session_state[audio_keys["audio_name"]],
                    )
                else:
                    st.toast("请先选择要处理的音频文件", icon=":material/error:")
                    st.stop()

                msg_ved.toast("音频预处理完成", icon=":material/graphic_eq:")

                print("\n\033[1;34m🚀 任务开始执行\033[0m")
                print(f"\033[1;34m📂 本次任务目录:\033[0m\033[1;34m {cache_dir} \033[0m")
                print("\033[1;33m⚠️ 请不要在任务运行期间切换菜单或修改参数！\033[0m")

                msg_whs = st.toast("正在识别音频内容", icon=":material/troubleshoot:")
                asr_client = ASRClient()
                sentences = asr_client.post(
                    ASRRequest(
                        file_path=Path(cache_dir / st.session_state[audio_keys["audio_name"]]),
                        model_name=qwen_model_name if asr_model_provider == "Qwen3-ASR" else None,
                    )
                )
                if not sentences:
                    error_message = (
                        asr_client.last_error or "识别失败，请检查音频文件格式是否正确，或尝试使用其他音频文件。"
                    )
                    _asr_logger.error(f"Streamlit ASR failed: {error_message}")
                    st.error(error_message, icon=":material/error:")
                else:
                    # 保存 response 到 json 文件
                    st.session_state[audio_keys["sentences"]] = sentences
                    # 保存字幕
                    print("\n\033[1;35m*** 正在生成 SRT 字幕文件 ***\033[0m\n")
                    st.session_state[audio_keys["preview_srt_file"]] = (
                        Path(asr_setting.output_dir) / "audio" / (audio_first_name + ".srt")
                    )
                    write_srt_from_sentences(
                        sentences,
                        st.session_state[audio_keys["preview_srt_file"]],
                    )
                    print("\033[1;34m🎉 字幕生成成功！\033[0m")
                    print("\033[1;34m🎉 ASR 识别成功！\033[0m")
                    msg_whs.toast("音频内容识别完成", icon=":material/colorize:")
                    print("\033[1;34m🎉 任务成功结束！\033[0m")
                print("\n" + "=" * 50 + "\n")
            else:
                st.toast("请先在工具栏中上传音频文件！", icon=":material/release_alert:")

    st.markdown("")
    with st.expander("**Audio Preview / 音轨预览**", expanded=True, icon=":material/graphic_eq:"):
        col6, col7 = st.columns([0.9999999, 0.0000001])
    with col6:
        # 2.2.1. 音轨预览
        st.caption("音频音轨")
        if st.session_state[audio_keys["use_example"]]:
            audio_file = st.session_state[audio_keys["audio_file"]]
            with Path(audio_file).open("rb") as f:
                audio_bytes = f.read()
            st.audio(audio_bytes)
        elif st.session_state[audio_keys["use_upload"]]:
            audio_data = st.session_state[audio_keys["audio_file"]].getbuffer()
            audio_bytes = st.session_state[audio_keys["audio_file"]].getvalue()
            st.audio(audio_bytes)
        elif st.session_state[audio_keys["use_bilibili"]]:
            audio_file = st.session_state[audio_keys["audio_file"]]
            with Path(audio_file).open("rb") as f:
                audio_bytes = f.read()
            st.audio(audio_bytes)
        else:
            st.info(
                "##### 音轨预览区域 \n\n&nbsp;**运行后自动显示 | 查看 [项目文档还没有噢](https://xnnehang.top/) | 加入 [交流群组，也还没有噢]()**",
                icon=":material/view_in_ar:",
            )
            st.markdown("")

    st.markdown("")
    col1, col2 = st.columns([0.75, 0.25])
    with col2:
        with st.expander("**Tool / 工具**", expanded=True, icon=":material/construction:"):
            # 2.2.4. 上传文件
            st.caption("上传文件")

            if st.button(
                "**上传音频文件**",
                use_container_width=True,
                type="primary",
                key="upload_audio_button",
            ):
                upload_audio()

            # 2.2.3. 字幕工具
            st.caption("字幕工具")

            if st.toggle("自定义字幕", False, key="custom_subtitle"):
                st.caption("所有自定义行为均在生成字幕后操作，请先生成字幕。")
                subtitle_speed = st.selectbox(
                    get_setting_title("subtitle_speed", AudioRecognizeSettings),
                    webui_setting.get_labels("subtitle_speed"),
                    index=webui_setting.get_index("subtitle_speed"),
                )
                st.caption("字幕单句长则慢，单句短则快")
                st.markdown("")
                if subtitle_speed == "快":
                    cut_line = st.slider(
                        get_setting_title("cut_line", ASRSettings),
                        min_value=100,
                        max_value=1000,
                        value=cut_line,
                        step=100,
                        key="cut_line",
                    )
                    st.caption("两个字间隔时长超过这个值分为两句。")
                    st.markdown("")
                if subtitle_speed == "慢":
                    combine_line = st.slider(
                        get_setting_title("combine_line", ASRSettings),
                        min_value=100,
                        max_value=1000,
                        value=combine_line,
                        step=100,
                        key="combine_line",
                    )
                    st.caption("两个字间隔时长小于这个值合并为一句。")
                    max_sentence_length = st.slider(
                        get_setting_title("max_sentence_length", ASRSettings),
                        min_value=5,
                        max_value=40,
                        value=max_sentence_length,
                        step=1,
                        key="max_sentence_length",
                    )
                    st.caption("单句最大长度，如果超过该长度就不再继续合并。")
                    st.markdown("")

                if st.session_state[audio_keys["sentences"]]:
                    sentences = st.session_state[audio_keys["sentences"]]
                    if subtitle_speed == "慢":
                        sentences = combine_sentences(
                            sentences,
                            max_sentence_length=max_sentence_length,
                            combine_line=combine_line,
                        )
                    elif subtitle_speed == "快":
                        sentences = cut_sentences(sentences, cut_line=cut_line)
                    else:
                        pass
                    if st.session_state[audio_keys["preview_srt_file"]]:
                        write_srt_from_sentences(
                            sentences=sentences,
                            srt_file_path=Path(st.session_state[audio_keys["preview_srt_file"]]),
                        )
                else:
                    st.toast(
                        "未生成字幕，或生成的字幕不支持自定义。",
                        icon=":material/error:",
                    )
                    st.toast(
                        "请到`参数设置`-> `输出类型` -> `带时间戳`",
                        icon=":material/error:",
                    )

            if st.button("**下载字幕**", use_container_width=True, type="primary"):
                if st.session_state[audio_keys["preview_srt_file"]]:
                    with st.session_state[audio_keys["preview_srt_file"]].open("r", encoding="utf-8") as srt_file:
                        srt_content = srt_file.read()
                    st.download_button(
                        label=st.session_state[audio_keys["preview_srt_file"]].name,
                        data=srt_content,
                        file_name=st.session_state[audio_keys["preview_srt_file"]].name,
                        mime="text/plain",
                    )

                else:
                    st.toast("未检测到字幕生成！", icon=":material/error:")
            st.divider()

    with col1:
        # 2.2.2. 字幕预览
        with st.expander(
            "**Subtitle Preview / 字幕预览**",
            expanded=True,
            icon=":material/subtitles:",
        ):
            if st.session_state[audio_keys["preview_srt_file"]]:
                st.caption("字幕时间轴")
                with st.session_state[audio_keys["preview_srt_file"]].open("r", encoding="utf-8") as srt_file:
                    srt_content = srt_file.read()
                srt_data = parse_srt_file(srt_content)
                st.dataframe(srt_data, hide_index=True)  # type: ignore
            elif st.session_state[audio_keys["text_result"]]:
                st.caption("提取到的文本")
                st.markdown(st.session_state[audio_keys["text_result"]])
            else:
                st.info(
                    "##### 结果预览区域 \n\n&nbsp;\n\n**生成完毕后会在此区域自动显示字幕时间轴**\n\n 运行前，请在右侧使用上传文件工具导入你的音频文件！ \n\n&nbsp;\n\n&nbsp;",
                    icon=":material/view_in_ar:",
                )
                st.markdown("")

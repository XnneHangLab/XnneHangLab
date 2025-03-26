from pathlib import Path
import datetime
import streamlit as st
import shutil

from uiya.utils.model import FunASRModel, generate_results
from uiya.BasicRunner.extractor import save_only_text_from_response
from uiya.BasicRunner.converter import convert_response_to_sentences
from uiya.BasicRunner.combiner import combine_sentences
from uiya.BasicRunner.cutter import cut_sentences
from uiya.utils.SrtHelper import write_srt_from_sentences
from uiya.styles.global_style import style
from uiya.utils.public import (
    parse_srt_file,
)
from uiya.utils.config import load_settings_file, write_settings_file
from uiya._dataclass import AudioSettings, RunnerSettings
from uiya.utils.get_font import read_font_data
from uiya.utils.config import get_setting_title
from uiya.utils.FFmpegHelper import file_to_wav


style()
settings: RunnerSettings = load_settings_file("global.toml", setting=RunnerSettings)
audio_settings: AudioSettings = load_settings_file("audio.toml", setting=AudioSettings)
fonts = read_font_data()

guide = st.session_state.get("guide", audio_settings.guide)
output_type = st.session_state.get("output_type", audio_settings.output_type)
subtitle_speed = st.session_state.get("subtitle_speed", audio_settings.subtitle_speed)


@st.dialog("使用提示")
def AudioReadme():
    st.markdown(
        """
    ## 欢迎首次使用 AI全自动音频翻译 功能！
    为了确保顺利运行并获得最佳体验，请关闭此弹窗后，前往页面中的**参数设置**模块，进行必要的参数配置。

    请务必根据您的需求及时调整设置，以提高翻译的准确性和效率。
    更多参考资源：
    - 📘 [相关教程](https://blog.chenyme.top/blog/aavt-install)
    - 📂 [项目地址](https://github.com/Chenyme-AAVT)
    - 💬 [交流群组](https://t.me/+j8SNSwhS7xk1NTc9)

    """
    )
    st.markdown("")
    if st.button(
        "**我已知晓&nbsp;&nbsp;&nbsp;本次不再弹出**",
        type="primary",
        use_container_width=True,
        key="guide",
    ):
        st.session_state.welcome = True
        st.rerun()


# 用于音频上传
if "audio_name" not in st.session_state:
    st.session_state.audio_name = None
if "use_upload" not in st.session_state:
    st.session_state.use_upload = False
if "use_example" not in st.session_state:
    st.session_state.use_example = False
if "selected_file" not in st.session_state:
    st.session_state.selected_file = None


# with_timestamp
if "response_with_timestamp" not in st.session_state:
    st.session_state.response_with_timestamp = None
if "text_result" not in st.session_state:
    st.session_state.text_result = None

if "preview_srt_file" not in st.session_state:
    st.session_state.preview_srt_file = None


# 用于消息提示
if "readme" not in st.session_state and audio_settings.guide == "open":
    AudioReadme()
    st.session_state.readme = True
if "welcome" in st.session_state:
    st.toast("欢迎使用 ~", icon=":material/verified:")
    del st.session_state["welcome"]
if "save" in st.session_state:
    st.toast("参数已成功保存", icon=":material/verified:")
    del st.session_state["save"]
if "upload" in st.session_state:
    st.toast("文件上传成功！", icon=":material/verified:")
    del st.session_state["upload"]

tab1, tab2 = st.tabs(["**音频识别**", "**参数设置**"])
with tab2:

    AudioSave = st.container()
    AudioSetting = st.container(border=True)

    with AudioSetting:
        guide = st.selectbox(
            get_setting_title("guide", AudioSettings),
            audio_settings.get_zh_option_list("guide"),
            index=audio_settings.get_index("guide"),
        )
        output_type = st.selectbox(
            get_setting_title("output_type", AudioSettings),
            audio_settings.get_zh_option_list("output_type"),
            index=audio_settings.get_index("output_type"),
        )
        st.caption("只有带时间戳的字幕才支持自定义字幕速度。")
    with AudioSave:
        col1, col2 = st.columns([0.75, 0.25])
        st.markdown("")
        with col2:
            st.markdown("")
            st.markdown("")
            if st.button("**保存更改**", use_container_width=True, type="primary"):
                audio_settings.zh_set_value("guide", guide)
                audio_settings.zh_set_value("output_type", output_type)
                write_settings_file("audio.toml", audio_settings)
                st.session_state.save = True
                st.rerun()
        with col1:
            st.markdown("")
            st.markdown("")
            st.markdown("### 参数设置")
            st.caption("Changing Parameter Settings")

with tab1:
    # 配置处理
    col1, col2 = st.columns([0.75, 0.25])  # 置顶标题、执行按钮流程模块

    # 标题模块
    with col1:
        st.markdown("")
        st.markdown("")
        st.subheader("AI 全自动音频识别")
        st.caption("AI Automatic Audio Recognize")

    # 执行按钮流程模块
    with col2:
        st.markdown("")
        st.markdown("")
        if st.button("**开始识别**", type="primary", use_container_width=True):
            if "audio_file" in st.session_state:
                audio_file = st.session_state.audio_file
                print("\n" + "=" * 50)
                print(
                    "\n\033[1;39m*** Auto-Caption-Generator-Offline 音频识别 ***\033[0m"
                )
                st.toast(
                    "任务开始执行！请勿在运行时切换菜单或修改参数!",
                    icon=":material/rocket_launch:",
                )

                msg_ved = st.toast("正在对音频进行预处理", icon=":material/graphic_eq:")
                current_time = datetime.datetime.now().strftime("_%Y%m%d%H%M%S")
                # 使用上传的音频文件
                if st.session_state.use_upload:
                    audio_first_name = audio_file.name.split(".")[0]
                    audio_last_name = audio_file.name.split(".")[-1]
                    st.session_state.audio_name = audio_file.name
                    st.session_state.cache_dir = (
                        Path(settings.cache_dir) / audio_first_name / current_time
                    )
                    cache_dir = st.session_state.cache_dir
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    # TODO 这里只是复制到了 cache_Dir ,实际上， 我们需要把它处理成 wav.
                    with (cache_dir / st.session_state.audio_name).open("wb") as file:
                        file.write(audio_file.getbuffer())
                    if audio_last_name != "wav":
                        msg_ved.toast(
                            "转转换音频为 wav 格式", icon=":material/graphic_eq:"
                        )
                        print("\n\033转换音频为 wav 格式\033[0m")
                        # 转换成接受的 wav
                        file_to_wav(
                            input_path=cache_dir / st.session_state.audio_name,
                            output_wav_path=cache_dir / (audio_first_name + ".wav"),
                        )
                        # 更正使用的文件名
                        st.session_state.audio_name = audio_first_name + ".wav"

                # 使用示例音频文件
                elif st.session_state.use_example:
                    if st.session_state.selected_file:
                        audio_first_name = st.session_state.selected_file.split(".")[0]
                        audio_last_name = st.session_state.selected_file.split(".")[-1]
                    else:
                        st.toast("请先选择示例文件", icon=":material/error:")
                        st.stop()
                    st.session_state.audio_name = st.session_state.selected_file
                    st.session_state.cache_dir = (
                        Path(settings.cache_dir) / audio_first_name / current_time
                    )
                    cache_dir = st.session_state.cache_dir
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(
                        Path(f"tests/{st.session_state.audio_name}"),
                        cache_dir / st.session_state.audio_name,
                    )
                    if audio_last_name != "wav":
                        msg_ved.toast(
                            "转换音频为 wav 格式", icon=":material/graphic_eq:"
                        )
                        print("\n\033转换音频为 wav 格式\033[0m")
                        # 转换成接受的 wav
                        file_to_wav(
                            input_path=cache_dir / st.session_state.audio_name,
                            output_wav_path=cache_dir / (audio_first_name + ".wav"),
                        )
                        # 更正使用的文件名
                        st.session_state.audio_name = audio_first_name + ".wav"
                else:
                    st.toast("请先上传音频文件", icon=":material/error:")
                    st.stop()

                msg_ved.toast("音频预处理完成", icon=":material/graphic_eq:")

                print("\n\033[1;34m🚀 任务开始执行\033[0m")
                print(
                    f"\033[1;34m📂 本次任务目录:\033[0m\033[1;34m {cache_dir} \033[0m"
                )
                print("\033[1;33m⚠️ 请不要在任务运行期间切换菜单或修改参数！\033[0m")

                msg_whs = st.toast("正在识别音频内容", icon=":material/troubleshoot:")
                if audio_settings.output_type == "with_timestamp":
                    Model = FunASRModel()
                    model = Model.full_version()
                    response_with_timestamp = generate_results(
                        model=model,
                        input_path=Path(cache_dir / st.session_state.audio_name),
                    )
                    # 保存 response 到 json 文件
                    st.session_state.response_with_timestamp = response_with_timestamp
                    sentences = convert_response_to_sentences(response_with_timestamp)
                    # 保存字幕
                    print("\n\033[1;35m*** 正在生成 SRT 字幕文件 ***\033[0m\n")
                    st.session_state.preview_srt_file = (
                        Path(settings.output_dir)
                        / "audio"
                        / (audio_first_name + ".srt")
                    )
                    write_srt_from_sentences(
                        sentences,
                        st.session_state.preview_srt_file,
                    )
                    print("\033[1;34m🎉 字幕生成成功！\033[0m")

                elif audio_settings.output_type == "without_timestamp":
                    Model = FunASRModel()
                    model = Model.full_version()
                    response = generate_results(
                        model=model,
                        input_path=cache_dir / st.session_state.audio_name,
                    )
                    msg_srt = st.toast("正在生成 txt 文件", icon=":material/edit_note:")
                    print("\n\033[1;35m*** 正在生成 txt 文件 ***\033[0m\n")
                    result = save_only_text_from_response(
                        response, output_dir=Path(settings.output_dir) / "audio"
                    )
                    st.session_state.text_result = result
                    msg_srt.toast("txt 文件生成完成", icon=":material/edit_note:")
                print("\033[1;34m🎉 FunASR 识别成功！\033[0m")
                msg_whs.toast("音频内容识别完成", icon=":material/colorize:")
                print("\033[1;34m🎉 任务成功结束！\033[0m")
                print("\n" + "=" * 50 + "\n")
            else:
                st.toast(
                    "请先在工具栏中上传音频文件！", icon=":material/release_alert:"
                )

    st.markdown("")
    with st.expander(
        "**Audio Preview / 音轨预览**", expanded=True, icon=":material/graphic_eq:"
    ):
        col6, col7 = st.columns([0.9999999, 0.0000001])
    with col6:
        st.caption("音频音轨")
        if st.session_state.use_example:
            audio_file = st.session_state.audio_file
            with open(audio_file, "rb") as f:
                audio_bytes = f.read()
            st.audio(audio_bytes)
        elif st.session_state.use_upload:
            audio_data = st.session_state.audio_file.getbuffer()
            audio_bytes = st.session_state.audio_file.getvalue()
            st.audio(audio_bytes)
        else:
            st.info(
                "##### 音轨预览区域 \n\n&nbsp;**运行后自动显示 | 查看 [项目文档](https://blog.chenyme.top/blog/aavt-install) | 加入 [交流群组](https://t.me/+j8SNSwhS7xk1NTc9)**",
                icon=":material/view_in_ar:",
            )
            st.markdown("")

    st.markdown("")
    col1, col2 = st.columns([0.75, 0.25])
    with col2:
        with st.expander(
            "**Tool / 工具**", expanded=True, icon=":material/construction:"
        ):
            st.caption("上传文件")

            @st.dialog("上传音频文件 / 选择示例文件")
            def upload_audio():
                st.markdown(
                    "在这里上传您需要处理的音频文件，该模块一次只能处理一个，多个会互相覆盖。"
                )
                st.markdown(
                    """暂时受限于我家下行带宽(90M),建议上传小文件,mp3,m4a 都可以。wav 太大了。"""
                )
                st.caption(
                    """该服务用 frp 内网穿透，你看到的上传进度条只是上传到服务器，服务器还得发到我的电脑，所以会卡100%（等待电脑下载到本地，超级久），所以请上传小文件试试水（<10MB）！！！"""
                )
                st.markdown("")

                audio_file = st.file_uploader(
                    "上传您的音频文件",
                    type=["mp3", "mpga", "m4a", "wav"],
                    label_visibility="collapsed",
                    accept_multiple_files=False,
                )
                st.markdown("")
                if st.button("**点击上传**", use_container_width=True, type="primary"):
                    if audio_file is None:
                        st.toast("请先上传文件", icon=":material/error:")
                        pass
                    else:
                        st.session_state.audio_file = audio_file
                        st.session_state.use_upload = True
                        st.session_state.upload = True
                        st.rerun()

                st.markdown(
                    "**PS:** 因为卡 100% 真的很影响体验，这里提供了示例文件（都存在我的电脑中，不需要上传）。"
                )
                st.caption(
                    "example1: [华容道迷宫 | 《20 Small Mazes》](https://www.bilibili.com/video/BV1Xzk3YPEd9)"
                )
                st.caption(
                    "example2: [【AI巴老师】难道看我失魂落魄，你竟然心动](https://www.bilibili.com/video/BV1314y1k73r/)"
                )
                st.caption("example3: AI生成的一个长音频,用于上行速度影响测试。")
                st.markdown("")
                st.caption("也欢迎你通知我你要补充的示例文件。")

                select_file = st.selectbox(
                    "选择示例文件",
                    [
                        "example1.wav",
                        "example2.m4a",
                        "example3.mp3",
                    ],
                )
                if st.button(
                    "**使用示例文件**", use_container_width=True, type="primary"
                ):
                    if select_file == "example1.wav":
                        st.session_state.audio_file = "tests/example1.wav"
                        st.session_state.selected_file = select_file
                        st.session_state.use_example = True
                        st.session_state.upload = True
                        st.rerun()
                    elif select_file == "example2.m4a":
                        st.session_state.audio_file = "tests/example2.m4a"
                        st.session_state.selected_file = select_file
                        st.session_state.use_example = True
                        st.session_state.upload = True
                        st.rerun()
                    elif select_file == "example3.mp3":
                        st.session_state.audio_file = "tests/example3.mp3"
                        st.session_state.selected_file = select_file
                        st.session_state.use_example = True
                        st.session_state.upload = True
                        st.rerun()

                st.markdown("")

            if st.button(
                "**文件上传**",
                use_container_width=True,
                type="primary",
                key="upload_audio_button",
            ):
                upload_audio()

            st.caption("字幕工具")

            if st.toggle("自定义字幕", False, key="custom_subtitle"):
                subtitle_speed = st.selectbox(
                    get_setting_title("subtitle_speed", AudioSettings),
                    audio_settings.get_zh_option_list("subtitle_speed"),
                    index=audio_settings.get_index("subtitle_speed"),
                )
                st.caption("快慢以实况视频建议快，课程视频建议慢。")
                st.markdown("")

                if st.session_state.response_with_timestamp:
                    response_with_timestamp = st.session_state.response_with_timestamp
                    sentences = convert_response_to_sentences(response_with_timestamp)
                    if subtitle_speed == "慢":
                        sentences = combine_sentences(
                            sentences,
                            max_sentence_length=settings.max_sentence_length,
                            combine_line=settings.combine_line,
                        )
                    elif subtitle_speed == "快":
                        sentences = cut_sentences(sentences, cutline=settings.cut_line)
                    else:
                        pass
                    if st.session_state.preview_srt_file:
                        write_srt_from_sentences(
                            sentences=sentences,
                            srt_file_path=Path(st.session_state.preview_srt_file),
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

                if st.session_state.preview_srt_file:
                    with st.session_state.preview_srt_file.open(
                        "r", encoding="utf-8"
                    ) as srt_file:
                        srt_content = srt_file.read()
                    st.download_button(
                        label=st.session_state.preview_srt_file.name,
                        data=srt_content,
                        file_name=st.session_state.preview_srt_file.name,
                        mime="text/plain",
                    )

                else:
                    st.toast("未检测到字幕生成！", icon=":material/error:")
            st.divider()

    with col1:
        with st.expander(
            "**Subtitle Preview / 字幕预览**",
            expanded=True,
            icon=":material/subtitles:",
        ):
            if st.session_state.preview_srt_file:
                st.caption("字幕时间轴")
                with st.session_state.preview_srt_file.open(
                    "r", encoding="utf-8"
                ) as srt_file:
                    srt_content = srt_file.read()
                srt_data = parse_srt_file(srt_content)
                st.dataframe(srt_data, hide_index=True)  # type: ignore
            elif st.session_state.text_result:
                st.caption("提取到的文本")
                st.markdown(st.session_state.text_result)
            else:
                st.info(
                    "##### 结果预览区域 \n\n&nbsp;\n\n**生成完毕后会在此区域自动显示字幕时间轴**\n\n 运行前，请在右侧使用上传文件工具导入你的音频文件！ \n\n&nbsp;\n\n&nbsp;",
                    icon=":material/view_in_ar:",
                )
                st.markdown("")

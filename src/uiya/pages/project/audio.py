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
    open_folder_in_explorer,
)
from uiya.utils.config import load_settings_file, write_settings_file
from uiya._dataclass import AudioSettings, RunnerSettings
from uiya.utils.get_font import read_font_data
from uiya.utils.config import get_setting_title


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
        st.session_state.readme = True
        st.session_state.welcome = True
        st.rerun()


if "use_upload" not in st.session_state:
    st.session_state.use_upload = False

if "use_example" not in st.session_state:
    st.session_state.use_example = False

if "srt_file" not in st.session_state:
    st.session_state.srt_file = None

if "readme" not in st.session_state and audio_settings.guide == "open":
    AudioReadme()
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
        st.caption("关闭指引，开启后每次重启就不会再弹出使用提示")
        st.markdown("")
        output_type = st.selectbox(
            get_setting_title("output_type", AudioSettings),
            audio_settings.get_zh_option_list("output_type"),
            index=audio_settings.get_index("output_type"),
        )
        st.markdown("")
        subtitle_speed = st.selectbox(
            get_setting_title("subtitle_speed", AudioSettings),
            audio_settings.get_zh_option_list("subtitle_speed"),
            index=audio_settings.get_index("subtitle_speed"),
        )
        st.caption("快慢以实况视频建议快，课程视频建议慢。")
        st.markdown("")

    with AudioSave:
        col1, col2 = st.columns([0.75, 0.25])
        st.markdown("")
        with col2:
            st.markdown("")
            st.markdown("")
            if st.button("**保存更改**", use_container_width=True, type="primary"):
                audio_settings.zh_set_value("guide", guide)
                audio_settings.zh_set_value("output_type", output_type)
                audio_settings.zh_set_value("subtitle_speed", subtitle_speed)
                write_settings_file("audio.toml", audio_settings)
                st.session_state.save = True
                st.rerun()
        with col1:
            st.markdown("")
            st.markdown("")
            st.markdown("### 更改参数设置")
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
                if st.session_state.use_upload:
                    st.session_state.audio_first_name = audio_file.name.split(".")[0]
                    st.session_state.audio_last_name = audio_file.name.split(".")[-1]
                    st.session_state.audio_name = audio_file.name
                    cache_dir = (
                        Path(settings.cache_dir)
                        / st.session_state.audio_first_name
                        / current_time
                    )
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    # TODO 这里只是复制到了 cache_Dir ,实际上， 我们需要把它处理成 wav.
                    with (cache_dir / st.session_state.audio_name).open("wb") as file:
                        file.write(audio_file.getbuffer())
                elif st.session_state.use_example:
                    st.session_state.audio_first_name = st.session_state.selected_file
                    st.session_state.audio_last_name = "wav"
                    st.session_state.audio_name = (
                        st.session_state.selected_file + ".wav"
                    )
                    cache_dir = (
                        Path(settings.cache_dir)
                        / st.session_state.audio_first_name
                        / current_time
                    )
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(
                        Path(f"tests/{st.session_state.selected_file}.wav"),
                        cache_dir / st.session_state.audio_name,
                    )
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
                if audio_settings.output_type == "without_timestamp":
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
                elif audio_settings.output_type == "with_timestamp":
                    Model = FunASRModel()
                    model = Model.full_version()
                    response = generate_results(
                        model=model,
                        input_path=Path(cache_dir / st.session_state.audio_name),
                    )
                    sentences = convert_response_to_sentences(response)
                    if audio_settings.subtitle_speed == "slow":
                        print("\n\033[1;35m*** 正在调整字幕速度 : 慢***\033[0m\n")
                        settings.combine = True
                        settings.cut = False
                        sentences = combine_sentences(
                            sentences,
                            combine_line=settings.combine_line,
                            max_sentence_length=settings.max_sentence_length,
                        )
                    elif audio_settings.subtitle_speed == "fast":
                        print("\n\033[1;35m*** 正在调整字幕速度 : 快***\033[0m\n")
                        settings.combine = False
                        settings.cut = True
                        sentences = cut_sentences(sentences, cutline=settings.cut_line)

                    msg_srt = st.toast(
                        "正在生成SRT字幕文件", icon=":material/edit_note:"
                    )
                    print("\n\033[1;35m*** 正在生成 SRT 字幕文件 ***\033[0m\n")
                    write_srt_from_sentences(
                        sentences,
                        Path(settings.output_dir)
                        / "audio"
                        / (st.session_state.audio_first_name + ".srt"),
                    )
                    st.session_state.srt_file = (
                        Path(settings.output_dir)
                        / "audio"
                        / (st.session_state.audio_first_name + ".srt")
                    )
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
                st.markdown("在这里上传您需要处理的视频文件。")
                st.markdown(
                    """请注意，**开始识别**后无法取消任务！请勿在执行时点击任何 `项目按钮` 或 `切换菜单`，以免导致识别报错！"""
                )
                st.markdown("")

                audio_file = st.file_uploader(
                    "上传您的音频文件",
                    type=["mp3", "mpga", "m4a", "wav"],
                    label_visibility="collapsed",
                )
                st.markdown("")
                if st.button("**点击上传**", use_container_width=True, type="primary"):
                    st.session_state.audio_file = audio_file
                    st.session_state.use_upload = True
                    st.session_state.upload = True
                    st.rerun()

                st.markdown(
                    "**PS:** 由于我的服务器的带宽限制，**上传真的需要非常非常久**(20MB需要1分钟哦)。所以只是体验的话你可以选择我的示例文件。"
                )
                st.caption(
                    "example1: [华容道迷宫 | 《20 Small Mazes》](https://www.bilibili.com/video/BV1Xzk3YPEd9)"
                )
                select_file = st.selectbox(
                    "选择示例文件",
                    [
                        "example1",
                    ],
                )
                if st.button(
                    "**使用示例文件**", use_container_width=True, type="primary"
                ):
                    if select_file == "example1":
                        st.session_state.audio_file = "tests/example1.wav"
                        st.session_state.selected_file = "example1"
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
            if st.button(
                "**打开目录**",
                use_container_width=True,
                type="primary",
                key="audio_open",
            ):
                try:
                    open_folder_in_explorer(Path(settings.output_dir) / "audio")
                    st.toast(
                        "注意：文件夹已成功打开，可能未置顶显示，请检查任务栏！",
                        icon=":material/task_alt:",
                    )
                except Exception as e:
                    print(e)
                    st.toast("未进行识别，目录尚未生成！", icon=":material/error:")
                pass

            if st.button("**下载字幕**", use_container_width=True, type="primary"):
                st.toast("未检测到字幕生成！", icon=":material/error:")
            st.divider()

    with col1:
        with st.expander(
            "**Subtitle Preview / 字幕预览**",
            expanded=True,
            icon=":material/subtitles:",
        ):
            if st.session_state.srt_file:
                st.caption("字幕时间轴")
                with st.session_state.srt_file.open("r", encoding="utf-8") as srt_file:
                    srt_content = srt_file.read()
                srt_data = parse_srt_file(srt_content)
                st.dataframe(srt_data)  # type: ignore
            else:
                st.info(
                    "##### 结果预览区域 \n\n&nbsp;\n\n**生成完毕后会在此区域自动显示字幕时间轴**\n\n 运行前，请在右侧使用上传文件工具导入你的音频文件！ \n\n&nbsp;\n\n&nbsp;",
                    icon=":material/view_in_ar:",
                )
                st.markdown("")

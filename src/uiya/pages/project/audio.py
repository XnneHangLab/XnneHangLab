import os
from pathlib import Path
import datetime
import streamlit as st

from uiya.utils.model import FunASRModel, generate_results
from uiya.BasicRunner.extractor import save_only_text_from_response
from uiya.BasicRunner.converter import convert_response_to_sentences
from uiya.utils.SrtHelper import write_srt_from_sentences
from uiya.styles.global_style import style
from uiya.utils.public import srt_to_ass, srt_to_vtt, srt_to_sbv
from uiya.utils.config import load_settings_file
from uiya._dataclass import AudioSettings, RunnerSettings
from uiya.utils.get_font import read_font_data


style()

settings: RunnerSettings = load_settings_file("global.toml", setting=RunnerSettings)
audio_settings: AudioSettings = load_settings_file("audio.toml", setting=AudioSettings)
fonts = read_font_data()


@st.dialog("使用提示")
def AudioReadme():
    st.markdown(
        """
    ## 欢迎首次使用 AI全自动音频翻译 功能！

    为了确保顺利运行并获得最佳体验，请关闭此弹窗后，前往页面中的**参数设置**模块，进行必要的参数配置。
    
    请务必根据您的需求及时调整设置，以提高翻译的准确性和效率。

    更多参考资源：
    - 📘 [相关教程](https://blog.chenyme.top/blog/aavt-install)
    - 📂 [项目地址](https://github.com/Chenyme/Chenyme-AAVT)
    - 💬 [交流群组](https://t.me/+j8SNSwhS7xk1NTc9)
    
    """
    )
    st.markdown("")

    if st.button(
        "**我已知晓&nbsp;&nbsp;&nbsp;不再弹出**",
        type="primary",
        use_container_width=True,
        key="blog_first_button",
    ):
        st.session_state.read = True
        st.rerun()
    st.markdown("")


whisper_mode = "OpenAIWhisper - API"


AudioReadme()
if "save" in st.session_state:
    st.toast("参数已成功保存", icon=":material/verified:")
    del st.session_state["save"]
if "read" in st.session_state:
    st.toast("欢迎使用 ~", icon=":material/verified:")
    del st.session_state["read"]
if "upload" in st.session_state:
    st.toast("文件上传成功！", icon=":material/verified:")
    del st.session_state["upload"]

tab1, tab2 = st.tabs(["**音频识别**", "**参数设置**"])
with tab2:

    @st.dialog("语言说明")
    def Audio_lang():
        st.markdown(
            "**强制指定视频语言会提高识别准确度，但也可能会造成识别出错。** \n\n`自动识别` - 自动检测语言 (Auto Detect) \n\n`zh` - 中文 (Chinese) - 中文 \n\n`en` - 英语 (English) - English \n\n`ja` - 日语 (Japanese) - 日本語 \n\n`th` - 泰语 (Thai) - ภาษาไทย \n\n`de` - 德语 (German) - Deutsch \n\n`fr` - 法语 (French) - français \n\n`ru` - 俄语 (Russian) - Русский \n\n`ko` - 韩语 (Korean) - 한국어 \n\n`vi` - 越南语 (Vietnamese) - Tiếng Việt \n\n`it` - 意大利语 (Italian) - Italiano \n\n`ar` - 阿拉伯语 (Arabic) - العربية \n\n`es` - 西班牙语 (Spanish) - Español \n\n`bn` - 孟加拉语 (Bengali) - বাংলা \n\n`pt` - 葡萄牙语 (Portuguese) - Português \n\n`hi` - 印地语 (Hindi) - हिंदी"
        )

    AudioSave = st.container()
    AudioSetting = st.container(border=True)

    with AudioSetting:
        st.markdown("##### 指引 ")
        st.selectbox("guide", ["关闭", "开启"], index=0, label_visibility="collapsed")
        st.markdown("关闭指引，开启后每次就不会再弹出使用提示")
        st.markdown("")
        st.markdown("##### 输出类型 ")
        mode = st.selectbox(
            "output_type",
            ["不含时间线的纯文本(txt)", "带时间线的字幕(srt/ass/att)"],
            index=0,
            label_visibility="collapsed",
        )
        st.markdown(
            "具体配置输出字幕类型请参见 `Project -> 音频识别 -> 音频识别 -> 更多功能`。 只有勾选带时间线的字幕才支持输出各种格式。"
        )
        st.markdown("")
        st.markdown("##### Subtitle 字幕速度配置 ")
        st.markdown("")
        st.selectbox("subtitle_speed", ["慢", "适中", "快"])
        st.markdown(
            "字幕速度快慢的衡量是一句和一句的之间的切换的速度，单句字幕越短，一般越快，单句字幕越长，一般越慢。"
        )
        st.markdown("实况视频建议快，课程视频建议慢。")
        st.markdown("")

    with AudioSave:
        col1, col2 = st.columns([0.75, 0.25])
        st.markdown("")
        with col2:
            st.markdown("")
            st.markdown("")
            if st.button("**保存更改**", use_container_width=True, type="primary"):
                pass
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
        st.subheader("AI 全自动音频翻译")
        st.caption("AI Automatic Audio Translation")

    # 执行按钮流程模块
    with col2:
        st.markdown("")
        st.markdown("")
        if st.button("**开始识别**", type="primary", use_container_width=True):
            if "uploaded_file_audio" in st.session_state:
                uploaded_file_audio = st.session_state.uploaded_file_audio
                print("\n" + "=" * 50)
                print("\n\033[1;39m*** Chenyme-AAVT AI音频识别 ***\033[0m")
                st.toast(
                    "任务开始执行！请勿在运行时切换菜单或修改参数!",
                    icon=":material/rocket_launch:",
                )

                msg_ved = st.toast("正在对音频进行预处理", icon=":material/graphic_eq:")
                current_time = datetime.datetime.now().strftime("_%Y%m%d%H%M%S")
                st.session_state.audio_name_original = uploaded_file_audio.name.split(
                    "."
                )[0]
                st.session_state.audio_name = (
                    "output." + uploaded_file_audio.name.split(".")[-1]
                )
                output_dir = (
                    Path(settings.cache_path)
                    / st.session_state.audio_name_original
                    / current_time
                )
                output_dir.mkdir(parents=True, exist_ok=True)
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
                with (output_dir / st.session_state.audio_name).open("wb") as file:
                    file.write(uploaded_file_audio.getbuffer())
                msg_ved.toast("音频预处理完成", icon=":material/graphic_eq:")

                print("\n\033[1;34m🚀 任务开始执行\033[0m")
                print(
                    f"\033[1;34m📂 本次任务目录:\033[0m\033[1;34m {output_dir} \033[0m"
                )
                print("\033[1;33m⚠️ 请不要在任务运行期间切换菜单或修改参数！\033[0m")

                msg_whs = st.toast("正在识别音频内容", icon=":material/troubleshoot:")
                if mode == "only_text":
                    Model = FunASRModel()
                    model = Model.only_txt()
                    response = generate_results(
                        model=model,
                        input_path=output_dir / st.session_state.audio_name,
                    )
                    result = save_only_text_from_response(
                        response, output_dir=output_dir
                    )
                elif mode == "full_version":
                    Model = FunASRModel()
                    model = Model.full_version()
                    response = generate_results(
                        model=model,
                        input_path=Path(output_dir / st.session_state.audio_name),
                    )
                    sentences = convert_response_to_sentences(response)
                    write_srt_from_sentences(sentences, output_dir / "output.srt")

                # if 'error' in result:
                #     print(f"\033[1;31m❌ Whisper识别异常: {result['error']}\033[0m")
                #     st.error(f"处理失败，错误信息：{result['error']}")
                #     st.stop()
                print("\033[1;34m🎉 Whisper 识别成功！\033[0m")
                msg_whs.toast("音频内容识别完成", icon=":material/colorize:")
                msg_srt = st.toast("正在生成SRT字幕文件", icon=":material/edit_note:")
                print("\n\033[1;35m*** 正在生成 SRT 字幕文件 ***\033[0m\n")
                st.session_state.output_file_audio = str(output_dir)

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

    st.markdown("")
    col1, col2 = st.columns([0.75, 0.25])
    with col2:
        with st.expander(
            "**Tool / 工具**", expanded=True, icon=":material/construction:"
        ):
            st.caption("上传文件")

            @st.dialog("上传音频文件")
            def upload_audio():
                st.markdown("在这里上传您需要处理的视频文件。")
                st.markdown(
                    "请注意，除关闭 CMD 外，执行任务后无法取消任务！请勿在执行时点击任何 项目按钮 或 切换菜单，以免导致识别报错！"
                )
                st.markdown("")
                uploaded_file_audio = st.file_uploader(
                    "上传您的音频文件",
                    type=["mp3", "mpga", "m4a", "wav"],
                    label_visibility="collapsed",
                )
                st.markdown("")
                if st.button("**点击上传**", use_container_width=True, type="primary"):
                    st.session_state.uploaded_file_audio = uploaded_file_audio
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
                "**保存修改**",
                use_container_width=True,
                type="primary",
                key="audio_change",
            ):
                try:
                    with open(
                        st.session_state.output_file_audio + "/output.srt",
                        "w",
                        encoding="utf-8",
                    ) as srt_file:
                        srt_file.write(st.session_state.srt_content_new_audio)
                    st.toast("已成功保存", icon=":material/task_alt:")
                except Exception as e:
                    print(e)
                    st.toast("未检测到运行后的字幕文件", icon=":material/error:")

            if st.button(
                "**打开目录**",
                use_container_width=True,
                type="primary",
                key="audio_open",
            ):
                try:
                    os.startfile(st.session_state.output_file_audio)
                    st.toast(
                        "注意：文件夹已成功打开，可能未置顶显示，请检查任务栏！",
                        icon=":material/task_alt:",
                    )
                except Exception as e:
                    print(e)
                    st.toast("未进行识别，目录尚未生成！", icon=":material/error:")
            st.divider()

            if st.toggle("**更多功能**"):
                st.caption("字幕轴高度")
                height = st.number_input(
                    "高度显示",
                    min_value=300,
                    step=100,
                    value=550,
                    label_visibility="collapsed",
                )
                st.session_state.height_audio = height
                st.caption("其他字幕格式")
                try:
                    captions_option = st.radio(
                        "更多字幕格式导出",
                        ("VTT", "ASS", "SBV"),
                        index=0,
                        label_visibility="collapsed",
                    )
                    if captions_option == "VTT":
                        vtt_content = srt_to_vtt(st.session_state.srt_content_new_audio)
                        st.download_button(
                            label="**VTT 下载**",
                            data=vtt_content.encode("utf-8"),
                            key="vtt_download",
                            file_name="output.vtt",
                            mime="text/vtt",
                            use_container_width=True,
                            type="primary",
                        )
                    elif captions_option == "ASS":
                        sbv_content = srt_to_ass(
                            st.session_state.srt_content_new_audio,
                            "Arial",
                            "18",
                            "#FFFFFF",
                        )
                        st.download_button(
                            label="**ASS 下载**",
                            data=sbv_content.encode("utf-8"),
                            key="ass_download",
                            file_name="output.ass",
                            mime="text/ass",
                            use_container_width=True,
                            type="primary",
                        )
                    elif captions_option == "SBV":
                        sbv_content = srt_to_sbv(st.session_state.srt_content_new_audio)
                        st.download_button(
                            label="**SBV 下载**",
                            data=sbv_content.encode("utf-8"),
                            key="sbv_download",
                            file_name="output.sbv",
                            mime="text/sbv",
                            use_container_width=True,
                            type="primary",
                        )
                except Exception as e:
                    print(e)
                    if st.button(
                        "**下载字幕**", use_container_width=True, type="primary"
                    ):
                        st.toast("未检测到字幕生成！", icon=":material/error:")

            if "height_audio" not in st.session_state:
                st.session_state.height_audio = 550

    with col1:
        with st.expander(
            "**Subtitle Preview / 字幕预览**",
            expanded=True,
            icon=":material/subtitles:",
        ):
            try:
                st.caption("字幕时间轴")
                with open(
                    st.session_state.output_file_audio + "/output.srt",
                    "r",
                    encoding="utf-8",
                ) as srt_file:
                    srt_content = srt_file.read()
                # srt_data1 = parse_srt_file(srt_content, srt_setting)
                # edited_data = st.data_editor(srt_data1, height=st.session_state.height_audio, hide_index=True, use_container_width=True)
                # srt_data2 = convert_to_srt(edited_data, srt_setting)
                # st.session_state.srt_content_new_audio = srt_data2
            except Exception as e:
                print(e)
                st.info(
                    "##### 结果预览区域 \n\n&nbsp;\n\n**生成完毕后会在此区域自动显示字幕时间轴**\n\n 运行前，请在右侧使用上传文件工具导入你的音频文件！ \n\n&nbsp;\n\n&nbsp;",
                    icon=":material/view_in_ar:",
                )
                st.markdown("")

    with col6:
        try:
            st.caption("音频音轨")
            audio_file = open(
                f"{st.session_state.output_file_audio}/{st.session_state.audio_name}",
                "rb",
            )
            audio_bytes = audio_file.read()
            st.audio(audio_bytes)
        except Exception as e:
            print(e)
            try:
                audio_bytes = st.session_state.uploaded_file_audio.getvalue()
                st.audio(audio_bytes)
            except Exception as e:
                print(e)
                st.info(
                    "##### 音轨预览区域 \n\n&nbsp;**运行后自动显示 | 查看 [项目文档](https://blog.chenyme.top/blog/aavt-install) | 加入 [交流群组](https://t.me/+j8SNSwhS7xk1NTc9)**",
                    icon=":material/view_in_ar:",
                )
                st.markdown("")

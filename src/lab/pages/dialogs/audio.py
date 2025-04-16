from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from uiya.utils.config import UiyaSetting, load_settings_file as load_uiya_settings_file

from lab._dataclass import RootAbsDir
from lab._session_keys import audio_keys
from lab.utils.config import load_settings_file

root_settings = load_settings_file("root.toml", setting=RootAbsDir)
uiya_settings = load_uiya_settings_file("uiya.toml", setting=UiyaSetting)
ROOT_DIR = root_settings.root_dir


# 函数内部应该避免以 st.session_state 为判断条件，除非，它是一个完整模块，从初始化到结束都在这个模块中。
# 但是 dialog 不会是一个完整模块
@st.dialog("使用提示")
def AudioReadme():
    st.markdown(
        """
    ## 欢迎使用 AI全自动音频翻译 功能！
    请务必根据您的需求及时调整设置，以提高翻译的准确性和效率。
    更多参考资源：
    - 📘 [相关教程还没出噢](https://xnnehang.top/)

    """
    )
    st.markdown("")
    if st.button(
        "**我已知晓&nbsp;&nbsp;&nbsp;本次不再弹出**",
        type="primary",
        use_container_width=True,
        key="guide",
    ):
        st.session_state[audio_keys["welcome"]] = True
        st.rerun()


@st.dialog("选择待处理音频")
def upload_audio():
    st.markdown("## 方式一:上传音频文件")
    st.markdown("在这里上传您需要处理的音频文件，该模块一次只能处理一个，多个会互相覆盖。")
    st.caption(
        """该服务用 frp 内网穿透,你看到的上传进度条只是上传到服务器,服务器还得发到我的电脑,所以会卡100%，所以请上传小文件试试水(<10MB)."""
    )
    # st.caption(
    #     """另外，如果有对德国(欧洲地区)速度较快(下载速度可以达到超过20MB/s,目前大概只有10MB/s)的代理也可以向我推荐。"""
    # )
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
            st.session_state[audio_keys["audio_file"]] = audio_file
            st.session_state[audio_keys["upload"]] = True
            st.session_state[audio_keys["use_upload"]] = True
            st.session_state[audio_keys["use_bilibili"]] = False
            st.session_state[audio_keys["use_example"]] = False
            st.rerun()

    st.markdown("## 方式二: 使用示例文件/无需等待上传")
    st.caption("example1: 截取了 example2 的第一句歌词， 我用来跑 CI/CD 的。")
    st.caption("example2: [【AI巴老师】难道看我失魂落魄,你竟然心动](https://www.bilibili.com/video/BV1314y1k73r/)")
    st.markdown("")

    audio_name = st.selectbox(
        "选择示例文件",
        [
            "example1.wav",
            "example2.m4a",
        ],
    )
    if st.button("**使用示例文件**", use_container_width=True, type="primary"):
        if audio_name == "example1.wav":
            st.session_state[audio_keys["audio_file"]] = "examples/example1.wav"
            st.session_state[audio_keys["audio_name"]] = audio_name
            st.session_state[audio_keys["use_example"]] = True
            st.session_state[audio_keys["use_bilibili"]] = False
            st.session_state[audio_keys["use_upload"]] = False
            st.rerun()
        elif audio_name == "example2.m4a":
            st.session_state[audio_keys["audio_file"]] = "examples/example2.m4a"
            st.session_state[audio_keys["audio_name"]] = audio_name
            st.session_state[audio_keys["use_example"]] = True
            st.session_state[audio_keys["use_bilibili"]] = False
            st.session_state[audio_keys["use_upload"]] = False
            st.rerun()

    st.markdown("## 方式三: 从 `b站视频下载` 模块导入")
    st.caption(
        """
        在 `b站视频下载` 模块中单独勾选 `音频` 项然后下载，可以在这里访问。
        """
    )
    # 找出所有的音频文件
    audio_paths_list: list[str] = []
    for root, _, files in os.walk(Path(ROOT_DIR) / "downloads"):
        for file in files:
            if file.endswith(".m4s") or file.endswith(".m4a") or file.endswith(".mp3"):
                audio_paths_list.append(str(Path(root) / file))
    audio_name_path_dict: dict[str, str] = {}
    for audio_path in audio_paths_list:
        audio_name = Path(audio_path).name
        audio_name_path_dict[audio_name] = audio_path
    if audio_paths_list:
        audio_name = st.selectbox(
            "选择音频文件",
            [Path(audio_path).name for audio_path in audio_paths_list],
            label_visibility="collapsed",
        )
        st.markdown("")
    else:
        audio_name = ""
        st.info(
            "##### 音频文件区域 \n\n&nbsp;\n\n**没有找到音频文件,请在 `b站视频下载` 模块中单独勾选 `音频` 项然后下载。**\n\n&nbsp;\n\n&nbsp;",
            icon=":material/view_in_ar:",
        )
        st.markdown("")

    if st.button("选择该音频文件", use_container_width=True, type="primary"):
        if audio_name:
            st.session_state[audio_keys["audio_name"]] = audio_name
            st.session_state[audio_keys["audio_file"]] = audio_name_path_dict[audio_name]
            st.session_state[audio_keys["use_bilibili"]] = True
            st.session_state[audio_keys["use_example"]] = False
            st.session_state[audio_keys["use_upload"]] = False
            st.rerun()
        else:
            st.toast("请先选择音频文件", icon=":material/error:")
            st.stop()

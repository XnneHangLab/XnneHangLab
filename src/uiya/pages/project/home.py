from __future__ import annotations

import requests
import streamlit as st

from uiya.styles.global_style import style

# 参数配置
style()
st.markdown("")


@st.dialog("欢迎使用")
def readme():
    st.markdown(
        """
    ## 非常感谢您来到我的 XnneHangLab 项目！
    本项目旨在提供一个简单易用的自动识别视频或者音频的辅助工具，帮助快速识别视频字幕。
    如果您需要更多帮助，可以参考以下资源：
    - 📂 [**项目地址**](https://github.com/MrXnneHang/Auto-Caption-Generate-Offline)
    感谢您的使用和支持～
    """
    )


readme()


st.toast("欢迎使用 ~", icon=":material/verified:")
GITHUB_API_URL = "https://api.github.com/repos/MrXnneHang/Auto-Caption-Generate-Offline"
try:
    response = requests.get(GITHUB_API_URL)
    data = response.json()
    st.session_state.stars = data["stargazers_count"]
except Exception as e:
    st.session_state.stars = ""
    st.toast(f"无法获取Github数据: {e}")


st.title("XnneHangLab v0.0.1")
st.caption(f" A Project Powered By @Xnnehang 🌟Stars {st.session_state.stars}🌟")

st.divider()

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
    - 📂 [**项目地址**](https://github.com/MrXnneHang/XnneHangLab)
    感谢您的使用和支持～
    """
    )


readme()


st.toast("欢迎使用 ~", icon=":material/verified:")
GITHUB_API_URL = "https://api.github.com/repos/MrXnneHang/XnneHangLab"
try:
    response = requests.get(GITHUB_API_URL)
    data = response.json()
    st.session_state.stars = data["stargazers_count"]
except Exception as e:
    st.session_state.stars = ""
    st.toast(f"无法获取Github数据: {e}")


st.title("XnneHangLab v0.0.1")
st.caption(f" A Project Powered By @Xnnehang 🌟Stars {st.session_state.stars}🌟")

st.html(
    """
<a href="https://xnnehang.top/">

<div align="center">
    <img src="https://fastly.jsdelivr.net/gh/MrXnneHang/blog_img/BlogHosting/img/25/02/202503312014744.svg" alt="魔女の实验室" width="270" height="180">
    """
)

# st.markdown(
#     """
# ## :question: 它为什么诞生 :question:

# 我对它的期望是可以满足我日常音频所需的完整的工具链，主要有:

# - :film_projector: **做视频:** 视频字幕生成 :arrow_right: 视频字幕速度调节和编辑 :arrow_right: 字幕内嵌或者导出

# - :ear: **啃生肉提高日语水平** b站视频下载 :arrow_right: 视频字幕生成 :arrow_right: 视频字幕翻译

# - :microphone: **tts/sts 数据集制作:** 音频字幕生成 :arrow_right: 自动裁剪音频 :arrow_right: 响度匹配 :arrow_right: 降噪 :arrow_right: 字幕再次生成

# - :microphone: **tts/sts 微调和语音生成:** 可能会把以前玩过的 Bert-ViTS2 集成进来，同样，也是做视频用。

# """
# )

# st.caption("""
# 我一直痴迷于数据集的制作，预处理和语音合成，而前阵子发现 [uv ](https://github.com/astral-sh/uv)和 [streamlit ](https://github.com/streamlit/streamlit)这俩神奇的工具。它可以让我以前不同的项目集成到一个项目中，分开管理，同时运行，而不是每次使用都要切换目录，激活环境。于是我打算整合以前的一些项目。

# 另外，也是我为了利用家里一台吃灰半年的台式机（i5-13490f + 32G + 4060ti-16G），把它当作算力源， 用 frp 和一个外国的服务器把该项目部署到了我的网站。让我可以在任何地方访问我的这个工具链。【当然你也可以轻度使用，重度的话建议部署本地...】
# """)

# st.markdown("""
# ## :sparkles: 为什么叫魔女の实验室 :sparkles:

# 我在写这个项目的时经常想到伊蕾娜她小时候认真学习魔法的样子。

# 我大概也是以那种心态在写这个项目吧。不知道后面能不能直接把这个当毕设了。
#     """)


# st.divider()

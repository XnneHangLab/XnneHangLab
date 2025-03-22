import os
import streamlit as st
from uiya.utils.get_font import get_font_data
from uiya.styles.global_style import style


def main():
    style(True)
    get_font_data()

    os.environ["KMP_DUPLICATE_LIB_OK"] = "True"  # 修复OMP

    st.session_state.verify = True

    if "verify" in st.session_state:
        pages = {
            "Home": [
                st.Page(
                    page="pages/project/home.py", title="主页", icon=":material/home:"
                ),
                st.Page(
                    "pages/setting/set.py", title="全局设置", icon=":material/settings:"
                ),
            ],
            "Project": [
                st.Page(
                    page="pages/project/audio.py",
                    title="音频识别",
                    icon=":material/graphic_eq:",
                ),
                #     st.Page(page="pages/project/video.py", title="视频识别", icon=":material/subscriptions:"),
                #     st.Page(page="pages/project/translate.py", title="字幕翻译", icon=":material/subtitles:"),
            ],
            # "Test": [
            #     st.Page("pages/tests/test.py", title="声音克隆", icon=":material/view_in_ar:"),
            #     st.Page(page="pages/tests/tools.py", title="辅助工具", icon=":material/construction:")
            # ],
        }

        pg = st.navigation(pages, position="sidebar")
        pg.run()


if __name__ == "__main__":
    main()

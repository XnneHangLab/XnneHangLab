from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.streamlit.style import style

style(True)


def main():
    os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    ROOT_DIR = Path(lab_settings.root.root_dir)

    # 所有页面路径基于 ROOT_DIR 计算
    PAGE_PATHS = {
        "home": ROOT_DIR / "src" / "lab" / "streamlit" / "project" / "home.py",
        "audio": ROOT_DIR / "src" / "lab" / "streamlit" / "project" / "audio.py",
        "settings": ROOT_DIR / "src" / "lab" / "streamlit" / "setting" / "set.py",
    }
    # 检查路径是否存在
    for name, path in PAGE_PATHS.items():
        if not path.exists():
            raise FileNotFoundError(f"Page '{name}' not found at: {path}")

    # 在 st.Page() 中使用字符串路径（确保是绝对路径的字符串形式）
    pages = {
        "Home": [
            st.Page(page=str(PAGE_PATHS["home"]), title="主页", icon=":material/home:"),
            st.Page(
                page=str(PAGE_PATHS["settings"]),
                title="全局设置",
                icon=":material/settings:",
            ),
        ],
        "Project": [
            st.Page(
                page=str(PAGE_PATHS["audio"]),
                title="音频识别",
                icon=":material/headset:",
            ),
        ],
    }
    pg = st.navigation(pages, position="sidebar")
    pg.run()


if __name__ == "__main__":
    main()

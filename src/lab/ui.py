from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from lab.config_manager import XnneHangLabSettings, load_settings_file
from lab.styles.global_style import style

style(True)


def main():
    os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    ROOT_DIR = Path(lab_settings.root.root_dir)

    # 所有页面路径基于 ROOT_DIR 计算
    PAGE_PATHS = {
        "home": ROOT_DIR / "src" / "lab" / "pages" / "project" / "home.py",
        "audio": ROOT_DIR / "src" / "lab" / "pages" / "project" / "audio.py",
        "settings": ROOT_DIR / "src" / "lab" / "pages" / "setting" / "set.py",
    }
    if lab_settings.package.bert_vits:
        PAGE_PATHS["bert-vits"] = ROOT_DIR / "packages" / "bert-vits" / "src" / "vits" / "bert_vits.py"
    if lab_settings.package.to_do_list:
        PAGE_PATHS["todo"] = ROOT_DIR / "packages" / "todo" / "src" / "todo" / "streamlit_to_do.py"
    if lab_settings.package.yutto_uiya:
        PAGE_PATHS["uiya"] = ROOT_DIR / "packages" / "yutto-uiya" / "src" / "uiya" / "yutto_uiya.py"
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
    if lab_settings.package.bert_vits:
        pages["Project"].append(
            st.Page(
                page=str(PAGE_PATHS["bert-vits"]),
                title="BERT-VITS",
                icon=":material/robot:",
            ),
        )
    if lab_settings.package.to_do_list:
        pages["Project"].append(
            st.Page(
                page=str(PAGE_PATHS["todo"]),
                title="待办事项/Roadmap",
                icon=":material/checklist:",
            )
        )
    if lab_settings.package.yutto_uiya:
        pages["Project"].append(
            st.Page(
                page=str(PAGE_PATHS["uiya"]),
                title="b站视频下载",
                icon=":material/graphic_eq:",
            )
        )
    pg = st.navigation(pages, position="sidebar")
    pg.run()


if __name__ == "__main__":
    main()

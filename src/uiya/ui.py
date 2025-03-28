import os
import streamlit as st
from uiya.utils.get_font import get_font_data
from uiya.utils.config import load_settings_file
from uiya._dataclass import RootAbsDir
from pathlib import Path
from uiya.styles.global_style import style

style(True)


def main():
    get_font_data()

    os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

    root_dir = load_settings_file("root.toml", RootAbsDir)
    ROOT_DIR = Path(root_dir.root_dir)

    # 所有页面路径基于 ROOT_DIR 计算
    PAGE_PATHS = {
        "home": ROOT_DIR / "src" / "uiya" / "pages" / "project" / "home.py",
        "audio": ROOT_DIR / "src" / "uiya" / "pages" / "project" / "audio.py",
        "settings": ROOT_DIR / "src" / "uiya" / "pages" / "setting" / "set.py",
        "todo": ROOT_DIR / "packages" / "todo" / "src" / "todo" / "todo.py",
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
                page=str(PAGE_PATHS["todo"]),
                title="待办事项/Roadmap",
                icon=":material/checklist:",
            ),
            st.Page(
                page=str(PAGE_PATHS["audio"]),
                title="音频识别",
                icon=":material/graphic_eq:",
            ),
        ],
    }
    pg = st.navigation(pages, position="sidebar")
    pg.run()


if __name__ == "__main__":
    main()

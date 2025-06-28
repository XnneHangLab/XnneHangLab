"""运行 Streamlit 应用前将当前项目的根目录绝对路径写入配置文件
因为 Streamlit 应用启动后，读取根目录绝对路径会默认变成 `.`, 无法访问 `packages`, 而 packages 存储了各自模块的 ui, 必须访问。
所以这里将根目录绝对路径写入配置文件 `root.toml` 中。在 Streamlit 启动前运行，然后供它全局使用。
"""

from __future__ import annotations

from pathlib import Path

from lab._dataclass import RootAbsDir
from lab.config_manager.config import load_settings_file, write_settings_file
from lab.utils.console.logger import Logger


def main():
    ROOT_DIR = Path(__file__).parent.parent.parent.parent
    settings = load_settings_file("root.toml", RootAbsDir)
    settings.root_dir = str(ROOT_DIR)
    Logger.info(f"Set root directory to {settings.root_dir}")

    write_settings_file("root.toml", settings)

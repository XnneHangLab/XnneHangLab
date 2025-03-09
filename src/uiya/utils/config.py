from __future__ import annotations

from pathlib import Path

import yaml
import os
import platform


def xdg_config_home() -> Path:
    if (env := os.environ.get("XDG_CONFIG_HOME")) and (path := Path(env)).is_absolute():
        return path
    home = Path.home()
    if platform.system() == "Windows":
        return home / "AppData"
    return home / ".config"


def search_for_settings_file() -> Path | None:
    settings_file = Path("acgo.yaml")
    if not settings_file.exists():
        settings_file = xdg_config_home() / "acgo.yaml"
    if not settings_file.exists():
        return None
    return settings_file


# 读取配置文件
def load_config() -> dict[str, bool | str]:
    """读取配置文件到字典"""
    path = search_for_settings_file()
    try:
        if path is None:
            raise FileNotFoundError("配置文件不存在")
        else:
            with path.open(encoding="utf-8") as f:
                return yaml.load(f, Loader=yaml.FullLoader)
    except FileNotFoundError:
        # 打印错误信息
        print(f"配置文件 {path} 不存在")
        return {}

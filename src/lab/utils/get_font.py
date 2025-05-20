# type:ignore
# Copyright (c) 2023 Chenyme
from __future__ import annotations

import platform
from pathlib import Path


# TODO 这一步似乎耗时挺久，应该改到第一次使用时获取，而不是每次都获取
def get_font_data():
    system_type = platform.system()
    path = Path("./config/font.txt")

    if system_type == "Windows":
        import re
        import winreg

        fonts = []
        key = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
        registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key, 0, winreg.KEY_READ)
        for i in range(0, winreg.QueryInfoKey(registry_key)[1]):
            font_name, font_path, _ = winreg.EnumValue(registry_key, i)
            clean_font_name = re.sub(r"\s*\(.*?\)\s*", "", font_name).strip()
            fonts.append(clean_font_name)
        winreg.CloseKey(registry_key)
        with path.open("w", encoding="utf-8") as file:
            for font in fonts:
                file.write(font + "\n")

    elif system_type in ["Darwin"]:
        # Lazy-import
        import re
        import subprocess

        result = subprocess.run(["system_profiler", "SPFontsDataType"], capture_output=True, text=True)
        output = result.stdout
        fonts = re.findall(r"Full Name: (.+)", output)
        with path.open("w", encoding="utf-8") as file:
            for font in fonts:
                file.write(font + "\n")

    elif system_type in ["Linux"]:
        # Lazy-import
        import subprocess

        result = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True)
        output = result.stdout
        fonts = output.split("\n")
        with path.open("w", encoding="utf-8") as file:
            for font in fonts:
                if font:
                    file.write(font + "\n")

    else:
        print(f"获取字体失败！尚未支持的操作系统: {system_type}")


def read_font_data():
    path = Path("./config/font.txt")
    with path.open(encoding="utf-8") as file:
        lines = file.readlines()
        fonts = [line.strip() for line in lines]
        return fonts

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from lab._typing import Packages


class PackagesSettings(BaseModel):
    funasr: Annotated[bool, Field(False, title="是否包含 funasr")]
    whisper: Annotated[bool, Field(False, title="是否包含 whisper")]
    to_do_list: Annotated[bool, Field(True, title="是否包含 todo_list")]
    yutto_uiya: Annotated[
        bool,
        Field(True, title="是否包含 yutto-uiya"),
    ]
    gpt_sovits: Annotated[bool, Field(True, title="是否包含 gpt-sovits")]

    def to_dict(self) -> Packages:
        """转换为 Packages 类型的字典"""
        return {
            "to_do_list": self.to_do_list,
            "yutto_uiya": self.yutto_uiya,
            "gpt_sovits": self.gpt_sovits,
            "funasr": self.funasr,
        }


# 运行 uv run package 可以恢复默认
def main():
    from lab.config_manager.config import (
        XnneHangLabSettings,
        load_settings_file,
        search_for_settings_file,
        write_settings_file,
    )

    package_settings_path = search_for_settings_file("package.toml")
    if package_settings_path is not None and package_settings_path.exists():
        package_settings_path.unlink()  # ensure load default
    package_settings = load_settings_file("package.toml", PackagesSettings)
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    lab_settings.package = package_settings
    write_settings_file("lab.toml", lab_settings)
    package_path = search_for_settings_file("package.toml")
    if package_path is not None and package_path.exists():
        package_path.unlink()  # remove package.toml

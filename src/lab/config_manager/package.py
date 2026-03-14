from __future__ import annotations

from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class Packages(TypedDict):
    asr: bool
    to_do_list: bool
    yutto_uiya: bool
    gpt_sovits: bool
    qwen_tts: bool
    memory_bench: bool


class PackagesSettings(BaseModel):
    asr: Annotated[bool, Field(False, title="是否启用 sherpa-onnx ASR 服务")]
    whisper: Annotated[bool, Field(False, title="是否启用 whisper")]
    to_do_list: Annotated[bool, Field(True, title="是否启用 todo_list")]
    yutto_uiya: Annotated[bool, Field(True, title="是否启用 yutto-uiya")]
    gpt_sovits: Annotated[bool, Field(True, title="是否启用 gpt-sovits")]
    qwen_tts: Annotated[bool, Field(False, title="是否启用 faster-qwen-tts")]
    memory_bench: Annotated[
        bool,
        Field(False, title="是否挂载 memory_bench 记忆服务 (路由前缀: /memory)"),
    ]

    def to_dict(self) -> Packages:
        """将配置模型转换为 Packages 字典。

        Args:
            None.

        Returns:
            Packages: 当前启用状态的字典表示。

        Raises:
            None.
        """
        return {
            "asr": self.asr,
            "to_do_list": self.to_do_list,
            "yutto_uiya": self.yutto_uiya,
            "gpt_sovits": self.gpt_sovits,
            "qwen_tts": self.qwen_tts,
            "memory_bench": self.memory_bench,
        }


def main() -> None:
    """重置 package 配置并写回到 lab.toml。

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    from lab.config_manager.config import (
        XnneHangLabSettings,
        load_settings_file,
        search_for_settings_file,
        write_settings_file,
    )

    package_settings_path = search_for_settings_file("package.toml")
    if package_settings_path is not None and package_settings_path.exists():
        package_settings_path.unlink()

    package_settings = load_settings_file("package.toml", PackagesSettings)
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    lab_settings.package = package_settings
    write_settings_file("lab.toml", lab_settings)

    package_path = search_for_settings_file("package.toml")
    if package_path is not None and package_path.exists():
        package_path.unlink()

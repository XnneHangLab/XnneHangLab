from __future__ import annotations

from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class Packages(TypedDict):
    sherpa_asr: bool
    qwen_asr: bool
    llm_translate: bool
    to_do_list: bool
    yutto_uiya: bool
    gpt_sovits: bool
    qwen_tts: bool
    memory_bench: bool


class PackagesSettings(BaseModel):
    sherpa_asr: Annotated[bool, Field(False, title="Whether to enable sherpa-onnx paraformer ASR service")]
    qwen_asr: Annotated[bool, Field(False, title="Whether to enable Qwen3-ASR service")]
    llm_translate: Annotated[
        bool,
        Field(False, title="LLM Translate", description="启用本地 LLM 翻译引擎"),
    ]
    to_do_list: Annotated[bool, Field(True, title="Whether to enable todo_list")]
    yutto_uiya: Annotated[bool, Field(True, title="Whether to enable yutto-uiya")]
    gpt_sovits: Annotated[bool, Field(True, title="Whether to enable gpt-sovits")]
    qwen_tts: Annotated[bool, Field(False, title="Whether to enable faster-qwen-tts")]
    memory_bench: Annotated[
        bool,
        Field(False, title="Whether to mount memory_bench service (route prefix: /memory)"),
    ]

    def to_dict(self) -> Packages:
        return {
            "sherpa_asr": self.sherpa_asr,
            "qwen_asr": self.qwen_asr,
            "llm_translate": self.llm_translate,
            "to_do_list": self.to_do_list,
            "yutto_uiya": self.yutto_uiya,
            "gpt_sovits": self.gpt_sovits,
            "qwen_tts": self.qwen_tts,
            "memory_bench": self.memory_bench,
        }


def main() -> None:
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

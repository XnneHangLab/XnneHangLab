from __future__ import annotations

from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class Packages(TypedDict):
    llm_translate: bool
    local_embedding: bool
    memory_bench: bool


class PackagesSettings(BaseModel):
    llm_translate: Annotated[
        bool,
        Field(False, title="LLM Translate", description="启用本地 LLM 翻译引擎"),
    ]
    local_embedding: Annotated[
        bool,
        Field(False, title="Whether to enable local GGUF embedding service"),
    ]
    memory_bench: Annotated[
        bool,
        Field(False, title="Whether to mount memory_bench service (route prefix: /memory)"),
    ]

    def to_dict(self) -> Packages:
        return {
            "llm_translate": self.llm_translate,
            "local_embedding": self.local_embedding,
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

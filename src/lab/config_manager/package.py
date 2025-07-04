from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from lab.config_manager.config import load_settings_file, search_for_settings_file


class PackagesSettings(BaseModel):
    todo_list: Annotated[bool, Field(True, title="是否包含 todo_list")]
    yutto_uiya: Annotated[
        bool,
        Field(True, title="是否包含 yutto-uiya"),
    ]
    bert_vits: Annotated[bool, Field(True, title="是否 bert-vits")]
    vtuber: Annotated[
        bool,
        Field(True, title="是否包含 vtuber"),
    ]


def main():
    path = search_for_settings_file("package.toml")
    if path is not None:
        path.unlink()
    load_settings_file("package.toml", PackagesSettings)

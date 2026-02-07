# 我们这里所有的 MCP server 均用 streamable-http 连接不使用 stdio.
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class VtuberSettings(BaseModel):
    system_config: Annotated[
        str, Field("system_config.json", title="系统配置", description="系统配置文件路径，默认为 system_config.json")
    ]


def main():
    from lab.config_manager.config import (
        XnneHangLabSettings,
        load_settings_file,
        search_for_settings_file,
        write_settings_file,
    )

    vtuber_settings_path = search_for_settings_file("vtuber.toml")
    if vtuber_settings_path is not None and vtuber_settings_path.exists():
        vtuber_settings_path.unlink()  # ensure load default
    vtuber_settings = load_settings_file("vtuber.toml", VtuberSettings)
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    lab_settings.vtuber = vtuber_settings
    write_settings_file("lab.toml", lab_settings)
    vtuber_path = search_for_settings_file("vtuber.toml")
    if vtuber_path is not None and vtuber_path.exists():
        vtuber_path.unlink()  # remove vtuber.toml


if __name__ == "__main__":
    main()

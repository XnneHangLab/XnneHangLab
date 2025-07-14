# 我们这里所有的 MCP server 均用 streamable-http 连接不使用 stdio.
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class MCPServerSettingBase(BaseModel):
    transport: Annotated[Literal["http"], Field("http", title="MCP Transport")]
    host: Annotated[str, Field("127.0.0.1", title="MCP Host")]
    port: Annotated[int, Field(8080, title="MCP Port")]
    path: Annotated[str, Field("/", title="MCP Path")]
    log_level: Annotated[str, Field("debug", title="MCP Log Level")]


class TimeEmiServerSetting(MCPServerSettingBase):
    # 存储文件持久特殊变量.
    port: Annotated[int, Field(4200, title="MCP Port")]


class VisionServerSetting(MCPServerSettingBase):
    # 存储文件持久特殊变量.
    port: Annotated[int, Field(4201, title="MCP Port")]


class MCPSettings(BaseModel):
    timeemi: Annotated[TimeEmiServerSetting, Field(TimeEmiServerSetting())]  # pyright: ignore[reportCallIssue]
    vision: Annotated[VisionServerSetting, Field(VisionServerSetting())]  # pyright: ignore[reportCallIssue]


def main():
    from lab.config_manager.config import (
        XnneHangLabSettings,
        load_settings_file,
        search_for_settings_file,
        write_settings_file,
    )

    agent_settings_path = search_for_settings_file("agent.toml")
    if agent_settings_path is not None and agent_settings_path.exists():
        agent_settings_path.unlink()  # ensure load default
    mcp_settings = load_settings_file("mcp.toml", MCPSettings)
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    lab_settings.mcp = mcp_settings
    write_settings_file("lab.toml", lab_settings)
    mcp_path = search_for_settings_file("mcp.toml")
    if mcp_path is not None and mcp_path.exists():
        mcp_path.unlink()  # remove agent.toml


if __name__ == "__main__":
    main()

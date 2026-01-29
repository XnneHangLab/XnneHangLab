# 我们这里所有的 MCP server 均用 streamable-http 连接不使用 stdio.
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class MCPServerSettingBase(BaseModel):
    transport: Annotated[Literal["http"], Field("http", title="MCP Transport")]
    enable: Annotated[bool, Field(True, title="Enable MCP Server")]
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


class ToolServerSetting(MCPServerSettingBase):
    # 存储文件持久特殊变量.
    port: Annotated[int, Field(4202, title="MCP Port")]


class MCPServerSettings(BaseModel):
    timeemi: Annotated[TimeEmiServerSetting, Field(TimeEmiServerSetting())]  # pyright: ignore[reportCallIssue]
    vision: Annotated[VisionServerSetting, Field(VisionServerSetting())]  # pyright: ignore[reportCallIssue]
    tool: Annotated[ToolServerSetting, Field(ToolServerSetting())]  # pyright: ignore[reportCallIssue]


WebSearchProvider = Literal["duckduckgo", "searxng", "tavily", "bochaai"]


class WebSearchToolSettings(BaseModel):
    provider: Annotated[WebSearchProvider, Field("duckduckgo", title="Web Search Provider")]
    timeout_s: Annotated[float, Field(10.0, title="Web Search Timeout (s)")]
    searxng_url: Annotated[
        str, Field("http://127.0.0.1:8080", title="SearXNG URL")
    ]  # SearXNG 本地服务地址（当 provider="searxng" 时使用）
    tavily_api_key: Annotated[
        str, Field("", title="Tavily API Key")
    ]  # Tavily API key（当 provider="tavily" 时使用；不用可留空）
    bochaai_api_key: Annotated[
        str, Field("", title="BochaAI API Key")
    ]  # 博查得 API key（当 provider="bochaai" 时使用；不用可留空）


class WebFetchToolSettings(BaseModel):
    respect_robots: Annotated[bool, Field(True, title="Respect robots.txt")]
    robots_fail_closed: Annotated[bool, Field(False, title="Robots.txt Fail Closed")]
    use_jina_fallback: Annotated[bool, Field(False, title="Use Jina Fallback")]
    jina_api_key: Annotated[str, Field("", title="Jina API Key")]
    timeout_s: Annotated[float, Field(10.0, title="Web Fetch Timeout (s)")]
    max_chars_default: Annotated[int, Field(8000, title="Default Max Chars")]  # 可选


class MCPToolSettings(BaseModel):
    web_search: Annotated[WebSearchToolSettings, Field(WebSearchToolSettings())]  # pyright: ignore[reportCallIssue]
    web_fetch: Annotated[WebFetchToolSettings, Field(WebFetchToolSettings())]  # pyright: ignore[reportCallIssue]
    user_agent: Annotated[str, Field("XnneHangLab-MCP/1.1", title="User Agent")]  # 自定义 User-Agent


class MCPSettings(BaseModel):
    servers: Annotated[MCPServerSettings, Field(MCPServerSettings())]  # pyright: ignore[reportCallIssue]
    tools: Annotated[MCPToolSettings, Field(MCPToolSettings())]  # pyright: ignore[reportCallIssue]


def main():
    from lab.config_manager.config import (
        XnneHangLabSettings,
        load_settings_file,
        search_for_settings_file,
        write_settings_file,
    )

    mcp_settings_path = search_for_settings_file("mcp.toml")
    if mcp_settings_path is not None and mcp_settings_path.exists():
        mcp_settings_path.unlink()  # ensure load default
    mcp_settings = load_settings_file("mcp.toml", MCPSettings)
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    lab_settings.mcp = mcp_settings
    write_settings_file("lab.toml", lab_settings)
    mcp_path = search_for_settings_file("mcp.toml")
    if mcp_path is not None and mcp_path.exists():
        mcp_path.unlink()  # remove agent.toml


if __name__ == "__main__":
    main()

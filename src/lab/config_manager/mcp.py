# 我们这里所有的 MCP server 均用 streamable-http 连接不使用 stdio.
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


WebSearchProvider = Literal["duckduckgo", "searxng"]


class WebSearchToolSettings(BaseModel):
    provider: Annotated[WebSearchProvider, Field("duckduckgo", title="Web Search Provider")]
    timeout_s: Annotated[float, Field(10.0, title="Web Search Timeout (s)")]
    searxng_url: Annotated[
        str, Field("http://127.0.0.1:8000", title="SearXNG URL")
    ]  # SearXNG 本地服务地址（当 provider="searxng" 时使用）


# -----------------------------
# Config with validation
# -----------------------------
# TODO Move to lab.toml
class ToolContextConfig(BaseModel):
    """
    ToolContextConfig = 控制“tool model 上下文构建策略”的配置。

    目标
    - 在“工具 schema + 思考空间 + pinned state + 上下文窗口”之间做预算分配，
      避免把 tool model 喂到很慢/很贵/注意力分散，同时保证在需要时能看见关键历史。

    重要：这个 config 不会自动生效
    - 只有当你实现并调用类似 `build_tool_context(...)` / `trim_to_budget(...)` 的逻辑时，
      这些字段才会真正影响 tool_loop_messages。
    - 如果你只是定义了 config 但仍然用“system + 最后一条 user_input”喂给 tool model，
      那这些参数几乎不会起作用。

    字段说明（建议实现时的使用方式）
    - tool_budget_tokens:
        tool model 输入的粗预算（保守值）。注意工具 schema/函数定义也会占用大量 token。
    - reserve_tokens:
        预留给工具 schema、工具调用协议、模型思考余量的预算；用于从 budget 中先扣掉。
        validator 保证 reserve_tokens < tool_budget_tokens。
    - min_window_tokens:
        给“最近上下文窗口”保底的最小预算，防止 pinned state 或其它内容把窗口挤没。
    - pinned_max_chars:
        pinned state 的字符上限（第二道保护），防止 state JSON 过大影响速度与稳定性。
    - recent_n_msgs:
        当需要历史上下文时，最多向前带多少条 message（user/assistant/tool 都算）。
        工程实现建议：
          1) 先拿最近 N 条作为候选窗口；
          2) 再根据 token 预算逐步裁剪（而不是死保 N 条）。
    - include_prev_assistant:
        处理“对/不是/第二个/同样/继续”等强依赖上一轮 assistant 的短输入时，
        尽量把“上一条 assistant”也纳入窗口，以提升指代/选择解析的稳定性。
        工程注意：
          - 永远对索引做 clamp：即使历史不足也不要越界（避免 list index out of range）。
          - 若上一条 assistant 是 tool_calls 产物，确保协议顺序仍然正确（不要把 user 插到 tool messages 中间）。

    推荐的上下文构建流程（实现提示）
    1) 固定注入 system_prompt（tool router prompt）
    2) 固定注入 pinned state（ConversationState.to_tool_pinned_json 的一条消息）
    3) 依据 user_text 判断是否 context-dependent：
         - 否：窗口可只保留最后 rememberable 的少量消息（甚至只保 last user）
         - 是：扩展到 recent_n_msgs，并按 include_prev_assistant 做补齐
    4) 按 tool_budget_tokens/reserve_tokens 做粗裁剪，必要时对窗口做缩短/摘要替代

    这套配置的价值
    - 在“总是全上下文（慢）”与“永远短上下文（容易跑偏）”之间提供可调的工程折中。
    """

    model_config = ConfigDict(extra="forbid")
    # 粗估 token 预算（工具 schema + 思考也会占用，所以别给太满）
    tool_budget_tokens: Annotated[
        int, Field(default=2200, ge=512, le=20000, title="Tool Model Context Budget (tokens)")
    ]
    # 需要扩展时，最多向前带多少条 message（user/assistant/tool 都算）
    recent_n_msgs: Annotated[int, Field(default=10, ge=1, le=60, title="Recent Messages to Include")]
    # 扩展时是否尽量保证带上“上一条 assistant”（对“对/不是/第二个”很关键）
    include_prev_assistant: Annotated[bool, Field(True, title="Include Previous Assistant")]
    # pinned state 最大字符数（保护上限）
    pinned_max_chars: Annotated[int, Field(default=2400, ge=256, le=20000, title="Pinned State Max Characters")]
    # 预留 token 给工具 schema/模型思考（粗估）
    reserve_tokens: Annotated[
        int, Field(default=350, ge=0, le=5000, title="Reserve Tokens for Tool Schema and Thinking")
    ]
    # “窗口”最小保留预算（避免全被 pinned 吃掉）
    min_window_tokens: Annotated[int, Field(default=200, ge=0, le=5000, title="Minimum Window Tokens")]

    @field_validator("reserve_tokens")
    @classmethod
    def _reserve_lt_budget(cls, v: int, info) -> int:  # type: ignore
        # 在 pydantic v2 里拿到同模型其它字段要用 info.data
        budget = int(info.data.get("tool_budget_tokens", 2200))  # type: ignore
        if v >= budget:
            raise ValueError(f"reserve_tokens({v}) must be < tool_budget_tokens({budget})")
        return v


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
    tool_context: Annotated[ToolContextConfig, Field(ToolContextConfig())]  # pyright: ignore[reportCallIssue]


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

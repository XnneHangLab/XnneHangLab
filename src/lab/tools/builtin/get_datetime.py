from __future__ import annotations

from datetime import datetime
from typing import Any

from lab.tools.base import BuiltinTool
from lab.tools.types import AgentContext, ToolResult


class GetDatetimeTool(BuiltinTool):
    """
    返回当前日期和时间（本地时区）。

    替代原 timeemi MCP server 的 get_date_and_time 工具。
    原来走 HTTP MCP 调用，现在直接 datetime.now()，零开销。
    """

    name = "get_datetime"
    description = "Get the current date and time. Returns format: YYYY-MM-DD HH:MM:SS"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return ToolResult(ok=True, text=now, data={"datetime": now})

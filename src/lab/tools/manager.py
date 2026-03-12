from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

from lab.tools.types import AgentContext, ToolResult

if TYPE_CHECKING:
    from lab.tools.base import BuiltinTool


class ToolManager:
    """Manage builtin tools exposed to the agent."""

    def __init__(self) -> None:
        self._builtin: dict[str, BuiltinTool] = {}

    def register_builtin(self, tool: BuiltinTool) -> None:
        """Register or replace a builtin tool."""
        self._builtin[tool.name] = tool
        logger.debug(f"[ToolManager] registered builtin tool: {tool.name}")

    def build_system_prompt(
        self,
        *,
        preamble: str = "",
    ) -> str:
        sections: list[str] = []

        if preamble:
            sections.append(preamble.strip())

        tool_lines: list[str] = []
        for name, tool in self._builtin.items():
            tool_lines.append(f"### {name}")
            tool_lines.append(tool.description)
            if tool.usage_hint:
                tool_lines.append(f"> 使用时机：{tool.usage_hint}")
            tool_lines.append("")

        if tool_lines:
            sections.append("## 可用工具\n\n" + "\n".join(tool_lines).rstrip())

        return "\n\n".join(sections)

    def has_builtin(self, name: str) -> bool:
        return name in self._builtin

    def list_tools_schema(self) -> list[dict[str, Any]]:
        return [tool.get_schema() for tool in self._builtin.values()]

    async def call_tool(self, name: str, args: dict[str, Any] | str | None, ctx: AgentContext) -> ToolResult:
        if isinstance(args, str):
            try:
                parsed_args: dict[str, Any] = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError as exc:
                return ToolResult(ok=False, text="", error=f"invalid args JSON: {exc}")
        elif args is None:
            parsed_args = {}
        else:
            parsed_args = args

        if name not in self._builtin:
            return ToolResult(ok=False, text="", error=f"unknown tool: {name!r}")

        try:
            return await self._builtin[name].execute(parsed_args, ctx)
        except Exception as exc:
            logger.exception(f"[ToolManager] builtin tool {name!r} raised: {exc}")
            return ToolResult(ok=False, text="", error=f"{type(exc).__name__}: {exc}")

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

from lab.tools.types import AgentContext, ToolResult

if TYPE_CHECKING:
    from lab.tools.base import BuiltinTool


class ToolManager:
    """Manage builtin tools exposed to the agent."""

    _DEFAULT_TOOL_PREAMBLE = (
        "你可以使用工具来查询信息、读取外部状态或执行动作。\n"
        "工具纪律必须严格遵守：\n"
        "1. 当用户明确要求你调用、使用、查看某个工具时，你必须真的调用对应工具，不能口头假装已经调用。\n"
        "2. 只有在本轮收到工具成功结果后，你才能声称某个工具动作已经完成，或引用该工具看到的具体结果。\n"
        "3. 如果用户要求查看可选项、当前状态、列表、变量名或外部内容，先调用查询工具，再根据工具结果回答。\n"
        "4. 不要编造不存在的工具名、参数、返回值、变量名、状态或切换结果。\n"
        "5. 当记忆、常识、先前回复与工具结果冲突时，以本轮最新、最相关、成功的工具结果为准；如果仍不确定，就重新调用工具验证。\n"
        "6. 如果工具执行失败，要明确说明失败，不能把失败说成成功。"
    )

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
        include_default_preamble: bool = False,
    ) -> str:
        sections: list[str] = []

        if preamble:
            sections.append(preamble.strip())

        if include_default_preamble:
            sections.append(self._DEFAULT_TOOL_PREAMBLE.strip())

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

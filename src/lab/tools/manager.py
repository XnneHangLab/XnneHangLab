from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

from lab.tools.types import AgentContext, ToolResult

if TYPE_CHECKING:
    from lab.mcp import FastMcpRouter
    from lab.tools.base import BuiltinTool


class ToolManager:
    """
    统一工具管理器，聚合 BuiltinTools 和 McpTools（可选）。

    对外暴露两个核心接口：
    - list_tools_schema()  → 合并后的 OpenAI function schema 列表，可直接传给 LLM
    - call_tool(name, args, ctx) → 路由到内置工具或 MCP，返回 ToolResult

    设计原则：
    - Agent Loop 只跟 ToolManager 交互，不需要知道工具是内置的还是 MCP 的。
    - 内置工具优先级高于 MCP（同名时内置工具覆盖 MCP）。
    - MCP 是可选的：不传 mcp 参数时，只有内置工具可用。
    """

    def __init__(self, *, mcp: FastMcpRouter | None = None) -> None:
        self._builtin: dict[str, BuiltinTool] = {}
        self._mcp = mcp

    # ------------------------------------------------------------------
    # 注册接口
    # ------------------------------------------------------------------

    def register_builtin(self, tool: BuiltinTool) -> None:
        """注册一个内置工具。同名工具会被覆盖（后注册优先）。"""
        self._builtin[tool.name] = tool
        logger.debug(f"[ToolManager] registered builtin tool: {tool.name}")

    def build_system_prompt(
        self,
        *,
        preamble: str = "",
        include_mcp: bool = True,
    ) -> str:
        """
        根据已注册工具自动生成 tool system prompt。

        生成格式：
            {preamble}（可选引言，如"你是一个助手，你有以下工具可以使用："）

            ## 可用工具

            ### get_datetime
            获取当前时间和日期。
            > 使用时机：当用户询问当前时间、日期、今天是几号等时调用此工具。

            ### read_file
            ...

        参数：
        - preamble: 追加在工具列表前的引言段落（留空则直接从工具列表开始）
        - include_mcp: 是否在 prompt 中包含 MCP 工具（仅列出工具名和描述，无 usage_hint）

        注意：
        - 内置工具 description 和 usage_hint 均使用中文友好描述
        - MCP 工具没有 usage_hint，只列 description
        - 生成结果可直接作为 tool_system_prompt 传给 agent tool loop
        """
        sections: list[str] = []

        if preamble:
            sections.append(preamble.strip())

        tool_lines: list[str] = []

        # 先列 MCP 工具（如果有且 include_mcp）
        if include_mcp and self._mcp is not None:
            try:
                mcp_schemas: list[dict[str, Any]] = self._mcp.list_tools()  # type: ignore[attr-defined]
                for s in mcp_schemas:  # type: ignore[union-attr]
                    fn: dict[str, Any] = s.get("function", {})  # type: ignore[assignment]
                    name: str = fn.get("name", "")  # type: ignore[assignment]
                    desc: str = fn.get("description", "")  # type: ignore[assignment]
                    if name and name not in self._builtin:
                        tool_lines.append(f"### {name}")
                        if desc:
                            tool_lines.append(desc)  # type: ignore[arg-type]
                        tool_lines.append("")
            except Exception as e:
                logger.warning(f"[ToolManager] build_system_prompt: failed to list MCP tools: {e}")

        # 再列内置工具（内置工具有 usage_hint，描述更完整）
        for name, tool in self._builtin.items():
            tool_lines.append(f"### {name}")
            tool_lines.append(tool.description)
            if tool.usage_hint:
                tool_lines.append(f"> 使用时机：{tool.usage_hint}")
            tool_lines.append("")

        if tool_lines:
            sections.append("## 可用工具\n\n" + "\n".join(tool_lines).rstrip())

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Schema 接口
    # ------------------------------------------------------------------

    def has_builtin(self, name: str) -> bool:
        """判断给定工具名是否已注册为内置工具。"""
        return name in self._builtin

    def list_tools_schema(self) -> list[dict[str, Any]]:
        """
        返回所有可用工具的 OpenAI function schema 列表。

        合并顺序：先 MCP 工具，再内置工具（内置工具覆盖同名 MCP 工具）。
        调用方可直接传给 LLM 的 tools 参数。
        """
        schemas: dict[str, dict[str, Any]] = {}

        # MCP 工具（优先级低）
        if self._mcp is not None:
            try:
                mcp_schemas: list[dict[str, Any]] = self._mcp.list_tools()  # type: ignore[attr-defined]
                for s in mcp_schemas:  # type: ignore[union-attr]
                    name: str = s.get("function", {}).get("name", "")  # type: ignore[assignment]
                    if name:
                        schemas[name] = s
            except Exception as e:
                logger.warning(f"[ToolManager] failed to list MCP tools: {e}")

        # 内置工具（优先级高，覆盖同名 MCP）
        for name, tool in self._builtin.items():
            schemas[name] = tool.get_schema()

        return list(schemas.values())

    # ------------------------------------------------------------------
    # 执行接口
    # ------------------------------------------------------------------

    async def call_tool(self, name: str, args: dict[str, Any] | str | None, ctx: AgentContext) -> ToolResult:
        """
        路由并执行工具。

        - 内置工具优先。
        - 若非内置工具且 mcp 可用，转发给 MCP 执行。
        - args 支持 dict 或 JSON 字符串（兼容 LLM 直接传来的 JSON string）。

        返回 ToolResult，调用方根据 ok 字段判断是否成功。
        """
        # 参数解析：兼容 dict 和 JSON string
        if isinstance(args, str):
            try:
                parsed_args: dict[str, Any] = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError as e:
                return ToolResult(ok=False, text="", error=f"invalid args JSON: {e}")
        elif args is None:
            parsed_args = {}
        else:
            parsed_args = args

        # 内置工具路由
        if name in self._builtin:
            try:
                return await self._builtin[name].execute(parsed_args, ctx)
            except Exception as e:
                logger.exception(f"[ToolManager] builtin tool {name!r} raised: {e}")
                return ToolResult(ok=False, text="", error=f"{type(e).__name__}: {e}")

        # MCP 路由（回退）
        if self._mcp is not None:
            try:
                result_obj = await self._mcp.call_tool(full_name=name, args=parsed_args)  # type: ignore[attr-defined]
                # MCP 返回的是 FastMCP CallToolResult，提取 text
                is_error = bool(getattr(result_obj, "is_error", False))
                if is_error:
                    blocks = getattr(result_obj, "content", []) or []
                    err = next((getattr(b, "text", None) for b in blocks if getattr(b, "text", None)), "tool_error")
                    return ToolResult(ok=False, text="", error=err)
                data = getattr(result_obj, "data", None)
                text = str(data) if data is not None else ""
                return ToolResult(ok=True, text=text, data={"raw": data})
            except Exception as e:
                logger.exception(f"[ToolManager] MCP tool {name!r} raised: {e}")
                return ToolResult(ok=False, text="", error=f"{type(e).__name__}: {e}")

        return ToolResult(ok=False, text="", error=f"unknown tool: {name!r}")

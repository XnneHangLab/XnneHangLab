from __future__ import annotations

import json
from typing import Any

from lab.tools.base import BuiltinTool
from lab.tools.plugin import PromptSegment, ToolPlugin
from lab.tools.types import AgentContext, ToolResult


class _ListLive2DAppearancesTool(BuiltinTool):
    name = "list_live2d_appearances"
    description = "列出当前 Live2D 模型可用的持久形态/外观选项（发型预设、部件显隐等）"
    usage_hint = "当用户询问可以切换什么形态、发型、外观时调用"

    def __init__(self, appearance_map: dict[str, str]) -> None:
        self._appearance_map = appearance_map

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
        del args, ctx
        if not self._appearance_map:
            return ToolResult(ok=False, text="", error="当前模型没有可用的持久形态选项")

        lines = [f"- {display_name} -> {expression}" for display_name, expression in self._appearance_map.items()]
        return ToolResult(ok=True, text="可用形态:\n" + "\n".join(lines))


class _SetLive2DAppearanceTool(BuiltinTool):
    name = "set_live2d_appearance"
    description = "切换 Live2D 模型的持久形态/外观（如发型预设、显隐部件等）。切换后持续保持直到下次切换。"
    usage_hint = "当需要切换形态、发型、显隐部件时调用"

    def __init__(self, appearance_map: dict[str, str]) -> None:
        self._appearance_map = appearance_map

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appearance_key": {
                            "type": "string",
                            "description": "要切换到的形态名称（中文 key）",
                        }
                    },
                    "required": ["appearance_key"],
                },
            },
        }

    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        key = args.get("appearance_key")
        if not isinstance(key, str) or key not in self._appearance_map:
            available = list(self._appearance_map.keys())
            return ToolResult(ok=False, text="", error=f"无效的形态 key: {key}，可用: {available}")

        ws_send = ctx.extra.get("websocket_send")
        if callable(ws_send):
            await ws_send(
                json.dumps(
                    {
                        "type": "set-live2d-appearance",
                        "expression": self._appearance_map[key],
                    }
                )
            )

        return ToolResult(ok=True, text=f"已切换形态: {key}")


class Live2DControlPlugin(ToolPlugin):
    name = "live2d_control"
    description = "控制 Live2D 模型的持久形态切换"

    def __init__(self, appearance_keys: list[str] | None = None) -> None:
        self._appearance_keys = appearance_keys or []
        self._appearance_map: dict[str, str] = {}

    async def on_register(self, ctx: AgentContext) -> bool:
        emo_map = ctx.extra.get("live2d_emo_map", {})
        if not isinstance(emo_map, dict):
            self._appearance_map = {}
            return False

        self._appearance_map = {key: emo_map[key] for key in self._appearance_keys if key in emo_map}
        return bool(self._appearance_map)

    def get_tools(self) -> list[BuiltinTool]:
        return [
            _ListLive2DAppearancesTool(self._appearance_map),
            _SetLive2DAppearanceTool(self._appearance_map),
        ]

    def get_prompt_segments(self) -> list[PromptSegment]:
        return [
            PromptSegment(
                name="live2d_control",
                content=(
                    "你可以通过工具查看和切换角色的外观形态（如发型、部件显隐）。"
                    "形态切换是持久的，不需要在每句话里重复。"
                ),
            )
        ]

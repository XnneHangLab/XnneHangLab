from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, cast

from pydantic import Field, field_validator, model_validator

from lab.plugin.config import PluginConfigModel
from lab.tools.base import BuiltinTool
from lab.tools.plugin import PromptSegment, ToolPlugin
from lab.tools.types import AgentContext, ToolResult

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class AppearancePreset(PluginConfigModel):
    key: Annotated[str, Field(description="可切换的外观 key")]
    description: Annotated[str, Field(default="", description="该外观的说明文案")]

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("appearance_presets[].key must not be empty")
        return normalized


class Live2DControlPluginConfig(PluginConfigModel):
    appearance_presets: Annotated[
        list[AppearancePreset],
        Field(
            default_factory=list,
            description="可切换的 Live2D 外观预设列表。按当前顺序保存为对象列表。需要根据 model_dict 的 emotion map 实际情况写 key name。",
        ),
    ]

    @model_validator(mode="after")
    def validate_unique_keys(self) -> Live2DControlPluginConfig:
        seen: set[str] = set()
        for preset in self.appearance_presets:
            if preset.key in seen:
                raise ValueError(f"appearance_presets contains duplicate key: {preset.key}")
            seen.add(preset.key)
        return self


PLUGIN_CONFIG_MODEL = Live2DControlPluginConfig


@dataclass(frozen=True)
class AppearanceOption:
    expression: str
    description: str = ""


class _ListLive2DAppearancesTool(BuiltinTool):
    name = "list_live2d_appearances"
    description = "列出当前 Live2D 模型可用的持久形态/外观选项（发型预设、部件显隐等）"
    usage_hint = "当用户询问可以切换什么形态、发型、外观，或询问某个造型的区别时调用"

    def __init__(self, appearance_options: dict[str, AppearanceOption]) -> None:
        self._appearance_options = appearance_options

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
        if not self._appearance_options:
            return ToolResult(ok=False, text="", error="当前模型没有可用的持久形态选项")

        lines = ["可用形态:"]
        for display_name, option in self._appearance_options.items():
            line = f"- {display_name} -> {option.expression}"
            if option.description:
                line += f" | 说明: {option.description}"
            lines.append(line)

        return ToolResult(ok=True, text="\n".join(lines))


class _SetLive2DAppearanceTool(BuiltinTool):
    name = "set_live2d_appearance"
    description = "切换 Live2D 模型的持久形态/外观（如发型预设、显隐部件等）。切换后持续保持直到下次切换。"
    usage_hint = "当需要切换形态、发型、显隐部件时调用"

    def __init__(self, appearance_options: dict[str, AppearanceOption]) -> None:
        self._appearance_options = appearance_options

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
        if not isinstance(key, str) or key not in self._appearance_options:
            available = list(self._appearance_options.keys())
            return ToolResult(ok=False, text="", error=f"无效的形态 key: {key}，可用: {available}")

        ws_send = ctx.extra.get("websocket_send")
        if callable(ws_send):
            websocket_send = cast("Callable[[str], Awaitable[None]]", ws_send)
            await websocket_send(
                json.dumps(
                    {
                        "type": "set-live2d-appearance",
                        "expression": self._appearance_options[key].expression,
                    }
                )
            )

        return ToolResult(ok=True, text=f"已切换形态: {key}")


class Live2DControlPlugin(ToolPlugin):
    name = "live2d_control"
    config_model = Live2DControlPluginConfig
    description = "控制 Live2D 模型的持久形态切换"

    def __init__(self, appearance_presets: list[dict[str, str]] | list[AppearancePreset] | None = None) -> None:
        self._appearance_presets = [self._coerce_preset(preset) for preset in appearance_presets or []]
        self._appearance_options: dict[str, AppearanceOption] = {}

    @staticmethod
    def _coerce_preset(raw_preset: dict[str, str] | AppearancePreset) -> AppearancePreset:
        if isinstance(raw_preset, AppearancePreset):
            return raw_preset
        return AppearancePreset.model_validate(raw_preset)

    async def on_register(self, ctx: AgentContext) -> bool:
        raw_emo_map = ctx.extra.get("live2d_emo_map", {})
        if not isinstance(raw_emo_map, dict):
            self._appearance_options = {}
            return False

        typed_emo_map = cast("dict[object, object]", raw_emo_map)
        emo_map = {
            key: value for key, value in typed_emo_map.items() if isinstance(key, str) and isinstance(value, str)
        }

        self._appearance_options = {
            preset.key: AppearanceOption(
                expression=emo_map[preset.key],
                description=preset.description,
            )
            for preset in self._appearance_presets
            if preset.key in emo_map
        }
        return bool(self._appearance_options)

    def get_tools(self) -> list[BuiltinTool]:
        return [
            _ListLive2DAppearancesTool(self._appearance_options),
            _SetLive2DAppearanceTool(self._appearance_options),
        ]

    def get_prompt_segments(self) -> list[PromptSegment]:
        content_lines = [
            "你可以通过工具查看和切换角色的外观形态（如发型、部件显隐）。",
            "形态切换是持久的，不需要在每句话里重复。",
            "当用户询问某个造型是什么样、适合什么区别或想比较多个造型时，优先参考下面的造型说明，不要臆测未配置的信息。",
        ]

        if self._appearance_options:
            content_lines.append("当前可切换造型说明:")
            for display_name, option in self._appearance_options.items():
                if option.description:
                    content_lines.append(f"- {display_name}: {option.description}")
                else:
                    content_lines.append(f"- {display_name}: 未提供额外说明，仅按名称理解")

        return [
            PromptSegment(
                name="live2d_control",
                content="\n".join(content_lines),
            )
        ]

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from lab.plugin.config import PluginConfigModel
from lab.plugin.hook import PolicyPlugin
from lab.tools.plugin import PromptInjectionPosition, PromptSegment


class ToolCallIntegrityPluginConfig(PluginConfigModel):
    injection_position: Annotated[
        Literal["before_tools", "after_tools"],
        Field("before_tools", description="提示词注入位置，可选 before_tools 或 after_tools"),
    ]


PLUGIN_CONFIG_MODEL = ToolCallIntegrityPluginConfig


class ToolCallIntegrityPlugin(PolicyPlugin):
    def __init__(
        self,
        *,
        injection_position: Literal["before_tools", "after_tools"] = "before_tools",
    ) -> None:
        self._injection_position = PromptInjectionPosition(injection_position)

    def get_prompt_segments(self) -> list[PromptSegment]:
        lines = [
            "当需要使用工具时，必须发起系统提供的正式工具调用；不要用 `[list_dir ...]`、`[read_file ...]` 或其他普通文本假装已经调用工具。",
            "只能使用当前已注册工具中的真实工具名与参数；不要编造不存在的工具、参数、返回结构或调用结果。",
            "在收到本轮工具结果之前，不要声称已经看到了目录、文件、时间、网页或其他外部状态。",
            "如果工具失败、参数不确定，或结果不足以回答问题，应重试、改用其他已注册工具，或明确说明限制；不要猜测工具结果。",
        ]
        return [
            PromptSegment(
                name="工具调用完整性",
                content="\n".join(lines),
                priority=15,
                position=self._injection_position,
            )
        ]

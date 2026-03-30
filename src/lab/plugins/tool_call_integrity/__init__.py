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
            "调用工具时，严格遵循当前提供的 tools schema，包括工具名、参数名、必填项、参数类型与允许字段；不要自行补充 schema 中未定义的参数。",
            "只能使用当前已注册工具中的真实工具名与参数；不要编造不存在的工具、参数、返回结构或调用结果。",
            "当回答当前问题必须依赖工具时，你的下一步输出必须包含正式 tool call，而不是仅输出普通文本说明、伪工具语法或口头承诺；可以先给用户一句极短的前置说明，但随后必须立即发起正式 tool call。",
            "你负责发起 assistant tool call；工具执行结果会由系统以 tool message 回填。不要尝试自己伪造 tool response。",
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

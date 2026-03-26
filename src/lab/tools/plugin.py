from __future__ import annotations

from abc import ABC
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab.tools.base import BuiltinTool
    from lab.tools.types import AgentContext


class PromptInjectionPosition(StrEnum):
    BEFORE_TOOLS = "before_tools"
    AFTER_TOOLS = "after_tools"


class PromptSegment:
    def __init__(
        self,
        name: str,
        content: str,
        priority: int = 50,
        position: PromptInjectionPosition = PromptInjectionPosition.BEFORE_TOOLS,
    ):
        self.name = name
        self.content = content
        self.priority = priority
        self.position = position


class ToolPlugin(ABC):
    name: str
    description: str

    def get_tools(self) -> list[BuiltinTool]:
        return []

    def get_prompt_segments(self) -> list[PromptSegment]:
        return []

    async def on_register(self, ctx: AgentContext) -> bool:
        """返回 False 则静默跳过注册（不报错）。用于环境检测。"""
        return True

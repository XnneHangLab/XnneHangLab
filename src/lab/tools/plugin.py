from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lab.tools.base import BuiltinTool
    from lab.tools.types import AgentContext


class PromptSegment:
    def __init__(self, name: str, content: str, priority: int = 50):
        self.name = name
        self.content = content
        self.priority = priority


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

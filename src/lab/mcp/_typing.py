from __future__ import annotations

from typing import Any, Literal, TypedDict


class ToolMessage(TypedDict):
    role: Literal["tool"]
    content: str
    tool_call_id: str


class ToolInfo(TypedDict):
    tool_name: str
    tool_args: Any


class CommonMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str

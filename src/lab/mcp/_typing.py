from __future__ import annotations

from typing import Literal, TypedDict


class ToolMessage(TypedDict):
    role: Literal["tool"]
    content: str
    tool_call_id: str


class CommonMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str

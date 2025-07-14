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


class ImageMessage(TypedDict):
    role: Literal["user"]
    content: list[dict[str, Any]]


# message = {"role": "user", "content": [
#     {"type": "text", "text":"""
#     请用 2-3 句话描述图片，要求：
#     1. 第一句概括主要场景（如「这是一张办公室桌面的照片」）
#     2. 第二句补充关键细节（如「桌上有一台打开的笔记本电脑、一杯咖啡和几份文件」）
#     3. 如果图片中有文字或特殊物体，可以额外提及（如「屏幕上显示代码编辑器，可能是 Python」）
#     4. 语言自然，避免机械式描述
#     """},
#     {"type": "image_url",
#     "image_url": {
#         "url": f"data:image/jpeg;base64,{image_b64}"
#     }}
# ]}

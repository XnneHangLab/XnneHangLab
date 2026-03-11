from __future__ import annotations

import base64
import io
import math
from typing import Any

import pydantic
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from lab.tools.base import BuiltinTool
from lab.tools.plugin import PromptSegment, ToolPlugin
from lab.tools.types import AgentContext, ToolResult


class ScreenShotArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScreenShotResult(BaseModel):
    image_b64: str = Field(..., description="Current screen screenshot in base64 encoded JPEG.")


class _ScreenShotTool(BuiltinTool):
    name = "screen_shot"
    description = "Capture the current desktop screen and return a base64 encoded JPEG image."
    usage_hint = "当用户要求查看当前屏幕、桌面、窗口截图时调用此工具。"

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
        try:
            ScreenShotArgs.model_validate(args)
        except pydantic.ValidationError as exc:
            return ToolResult(ok=False, text="", error=str(exc))

        result = ScreenShotPlugin.capture()
        return ToolResult(ok=True, text=result.image_b64, data=result.model_dump(exclude_none=True, mode="json"))


class ScreenShotPlugin(ToolPlugin):
    name = "screen_shot"
    description = "Capture the current desktop screen and return a base64 encoded JPEG image."

    def __init__(self) -> None:
        self._tool = _ScreenShotTool()

    def get_tools(self) -> list[BuiltinTool]:
        return [self._tool]

    def get_prompt_segments(self) -> list[PromptSegment]:
        return [
            PromptSegment(
                name="describe_image",
                content=(
                    "先看清楚用户问什么，正面回答用户问题，比如能不能看到？先回答能看到或者不能，然后再回答你看到的内容（图片内容）。\n"
                    "如果用户不是问你图片具体内容或者具体是什么，那你可以选择性少回答一些。\n"
                    "而对于图片内容你可以这么回答。\n"
                    "1. 第一句概括主要场景\n"
                    "2. 第二句补充关键细节\n"
                    "3. 如果图片中有文字或特殊物体，可以额外提及特别是代码，可以区分它是 Python, 还是 txt 什么的，并且可以读出来一部分你感兴趣的。\n"
                    "4. 语言自然，避免机械式描述"
                ),
            )
        ]

    async def on_register(self, ctx: AgentContext) -> bool:
        try:
            from PIL import ImageGrab  # type: ignore[attr-defined]
        except Exception as exc:
            logger.info("Skip ScreenShotPlugin registration because ImageGrab is unavailable: {}", exc)
            return False
        return True

    @staticmethod
    def capture() -> ScreenShotResult:
        from PIL import Image, ImageGrab

        screenshot = ImageGrab.grab()
        if screenshot.mode in ("RGBA", "LA"):
            screenshot = screenshot.convert("RGB")

        original_width, original_height = screenshot.size
        scaling_factor = min(1280 / max(original_width, original_height), 1)
        if scaling_factor < 1:
            new_size = (math.ceil(original_width * scaling_factor), math.ceil(original_height * scaling_factor))
            screenshot = screenshot.resize(new_size, Image.LANCZOS)  # type: ignore[attr-defined]

        buffer = io.BytesIO()
        screenshot.save(buffer, "JPEG", quality=85)
        image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return ScreenShotResult(image_b64=image_b64)

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from .types import ImagePayload, ToolRunResult

if TYPE_CHECKING:
    from lab.agent.mcp_tool_loop import McpToolLoopRunner
    from lab.mcp import ConversationState, FastMcpRouter, ToolTraceItem


class ToolRunner:
    """封装 MCP tool loop：运行工具、收集 trace、抽取 tool 回调图（默认单张）。"""

    def __init__(
        self,
        *,
        mcp: FastMcpRouter,
        tool_loop: McpToolLoopRunner,
        state: ConversationState,
    ) -> None:
        self.mcp = mcp
        self.tool_loop = tool_loop
        self.state = state

    @staticmethod
    def _first_image_ref(tool_trace: list[ToolTraceItem]) -> str | None:
        """
        从 tool_trace 中提取第一个 image_ref。
        试图 match 这样一个对象：
        trace.raw_result = {
            "image_ref": tool_call.id,
            "mime": "image/jpeg",
            "b64_len": len(b64),
        }
        局限是：
        仅仅支持单图片场景，且 image_ref 必须在 raw_result 里。
        不过鉴于 openai 一次传入多个 image_url 的识别率直线下降（以前用 llm 做电池缺陷识别的经验），这里仅支持单图片场景，比如：
        调用 screen shoot，或者调用摄像机等工具，来获取图片，一般更建议多次调用然后每次对单张图片进行分析而不是一次调用获取多张图片。
        """
        for t in tool_trace:
            raw = t.raw_result or {}
            if isinstance(raw, dict):  # type: ignore
                if raw.get("kind") == "image_ref":
                    v = raw.get("image_ref")
                    if isinstance(v, str) and v:
                        return v
                v2 = raw.get("image_ref")
                if isinstance(v2, str) and v2:
                    return v2
        return None

    def _pick_tool_image_ref(self, tool_trace: list[ToolTraceItem]) -> str | None:
        """选择 tool 回调图策略：优先 last_image_ref，其次 trace 里第一个。"""
        img_ref = None
        refs = getattr(self.state, "refs", {})
        if isinstance(refs, dict):
            v = refs.get("last_image_ref")  # type: ignore
            if isinstance(v, str) and v:
                img_ref = v
        return img_ref or self._first_image_ref(tool_trace)

    def _load_tool_image(self, img_ref: str) -> ImagePayload | None:
        """从 blob_store 里取出 (b64, mime)。"""
        if img_ref in self.tool_loop.blob_store:
            blob = self.tool_loop.blob_store[img_ref]
            b64 = str(blob["b64"])
            mime = str(blob.get("mime", "image/jpeg"))
            return ImagePayload(label="tool1", b64=b64, mime=mime, source="tool")
        return None

    async def run_tool_loop_if_enabled(
        self,
        *,
        enable_tool: bool,
        tool_system_prompt: str,
        available_tools: list[dict[str, object]],
        user_input_text: str,
    ) -> ToolRunResult:
        """若 enable_tool=True，则运行 tool loop；否则返回空结果。"""
        if not enable_tool:
            return ToolRunResult(trace_json="(无)", tool_image=None, tool_trace=[])

        _, tool_trace = await self.tool_loop.run_tool_loop(
            tool_system_prompt=tool_system_prompt,
            available_tools=available_tools,
            debug=False,
            state=self.state,
            user_input=user_input_text,
        )

        trace_json = json.dumps(
            [t.model_dump(exclude_none=True, mode="json") for t in tool_trace],  # type: ignore[attr-defined]
            ensure_ascii=False,
            indent=2,
        )

        img_ref = self._pick_tool_image_ref(tool_trace)
        tool_image = self._load_tool_image(img_ref) if img_ref else None

        if img_ref and not tool_image:
            logger.warning(f"[TOOL] got image_ref={img_ref} but blob missing in blob_store")

        return ToolRunResult(trace_json=trace_json, tool_image=tool_image, tool_trace=tool_trace)

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from lab.mcp import ToolTraceItem


ImageSource = Literal["tool", "upload"]


@dataclass(frozen=True)
class ImagePayload:
    """内存中携带的一张图片（b64/mime），以及它的标签。

    label:
        用于对齐摘要与图片，例如 tool1 / p1 / p2 ...
    source:
        tool: 工具回调图（截图等）
        upload: 用户上传图
    """

    label: str
    b64: str
    mime: str
    source: ImageSource


@dataclass(frozen=True)
class ToolRunResult:
    """一次 tool loop 的结果（或未启用工具时的空结果）。"""

    trace_json: str
    tool_image: ImagePayload | None
    tool_trace: list[ToolTraceItem]


@dataclass(frozen=True)
class VisionSummaryResult:
    """vision 摘要结果：tool 单张摘要 + upload 多图摘要（label->summary）。"""

    tool_image_summary: str
    upload_summaries: dict[str, str]

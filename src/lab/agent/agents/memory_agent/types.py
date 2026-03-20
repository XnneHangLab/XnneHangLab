from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from lab.agent.types import ToolTraceItem


ImageSource = Literal["tool", "upload"]
DEFAULT_TOOL_IMAGE_LABEL = "tool1"


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
    """vision 摘要结果：tool 单张摘要 + upload 多图摘要（label->summary）。

    Args:
        tool_image_summary: 工具截图完整摘要文本。
        tool_image_brief: 工具截图一句话摘要；None 表示解析失败。
        upload_summaries: 用户上传图片完整摘要，label->full_summary。
        upload_briefs: 用户上传图片一句话摘要，label->brief；None 值表示该张解析失败。
    """

    tool_image_summary: str
    tool_image_brief: str | None
    upload_summaries: dict[str, str]
    upload_briefs: dict[str, str | None]

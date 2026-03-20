from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from lab.agent.types import ToolTraceItem


ImageSource = Literal["tool", "upload"]
DEFAULT_TOOL_IMAGE_LABEL = "tool1"
VisionAnalysisStatus = Literal["success", "unavailable", "provider_error", "timeout", "empty", "invalid", "exception"]


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
class VisionAnalysisOutcome:
    """单张图片的 vision 处理结果。"""

    status: VisionAnalysisStatus
    summary: str = ""
    brief: str | None = None
    detail: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "success"

    @classmethod
    def success(cls, *, summary: str, brief: str) -> VisionAnalysisOutcome:
        return cls(status="success", summary=summary, brief=brief)

    @classmethod
    def failure(
        cls,
        status: VisionAnalysisStatus,
        *,
        detail: str | None = None,
    ) -> VisionAnalysisOutcome:
        if status == "success":
            raise ValueError("VisionAnalysisOutcome.failure cannot use status='success'")
        return cls(status=status, detail=detail)


@dataclass(frozen=True)
class VisionSummaryResult:
    """vision 摘要结果：tool 单张结果 + upload 多图结果。"""

    tool_image: VisionAnalysisOutcome | None = None
    upload_images: dict[str, VisionAnalysisOutcome] = field(default_factory=dict)

    @property
    def tool_image_summary(self) -> str:
        return self.tool_image.summary if self.tool_image and self.tool_image.succeeded else ""

    @property
    def tool_image_brief(self) -> str | None:
        return self.tool_image.brief if self.tool_image and self.tool_image.succeeded else None

    @property
    def upload_summaries(self) -> dict[str, str]:
        return {label: outcome.summary for label, outcome in self.upload_images.items() if outcome.succeeded}

    @property
    def upload_briefs(self) -> dict[str, str | None]:
        return {label: outcome.brief for label, outcome in self.upload_images.items() if outcome.succeeded}

    @property
    def upload_failures(self) -> dict[str, VisionAnalysisOutcome]:
        return {label: outcome for label, outcome in self.upload_images.items() if not outcome.succeeded}

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003
from typing import Any


def _default_paths() -> list[Path]:
    return []


def _default_extra() -> dict[str, Any]:
    return {}


@dataclass
class AgentContext:
    """
    工具执行时的运行时上下文，由调用方（ToolManager / Agent Loop）注入。

    字段说明
    - workspace_root: 工具允许读写的根目录（安全边界）
    - allowed_paths: 额外允许访问的路径列表（默认为空，只用 workspace_root 约束即可）
    - profile_name: 当前加载的 profile 名称（如 "congyin" / "desktop_pet"）
    - extra: 未来扩展用的 K-V 袋（例如注入 memory_backend_url 等）
    """

    workspace_root: Path
    allowed_paths: list[Path] = field(default_factory=_default_paths)
    profile_name: str = "default"
    extra: dict[str, Any] = field(default_factory=_default_extra)


@dataclass
class ToolResult:
    """
    BuiltinTool.execute() 的统一返回类型。

    字段说明
    - ok: 执行是否成功
    - text: 回填给 LLM tool message 的文本内容（简短、信息密集）
    - data: 结构化结果（可选），供调用方做进一步处理或 trace
    - error: 错误描述（ok=False 时填写）
    """

    ok: bool
    text: str
    data: dict[str, Any] | None = None
    error: str | None = None

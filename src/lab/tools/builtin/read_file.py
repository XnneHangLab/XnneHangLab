from __future__ import annotations

from pathlib import Path
from typing import Any

from lab.tools.base import BuiltinTool
from lab.tools.types import AgentContext, ToolResult

_MAX_CHARS_CLAMP = (256, 20000)


def _clamp(v: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


class ReadFileTool(BuiltinTool):
    """
    读取工作区内的本地文件，支持按行范围截取。

    替代原 tool MCP server 的 read_file 工具。
    直接本地执行，安全边界由 ctx.workspace_root 控制。
    """

    name = "read_file"
    description = (
        "Read a local file from the workspace. "
        "Optionally specify start_line/end_line (1-based, inclusive). "
        "Returns file content as text."
    )
    usage_hint = "当需要读取本地文件内容时调用此工具。支持指定行范围。"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to workspace root, or absolute path inside workspace.",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "1-based start line (inclusive). Defaults to 1.",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "1-based end line (inclusive). Defaults to end of file.",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Max characters to return (clamped to 256-20000). Default 8000.",
                        },
                    },
                    "required": ["path"],
                },
            },
        }

    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        path_str: str = args.get("path", "")
        if not path_str:
            return ToolResult(ok=False, text="", error="path is required")

        start_line: int | None = args.get("start_line")
        end_line: int | None = args.get("end_line")
        max_chars: int = _clamp(args.get("max_chars", 8000), *_MAX_CHARS_CLAMP)

        root = ctx.workspace_root.resolve()
        p = Path(path_str).expanduser()
        target = (root / p).resolve() if not p.is_absolute() else p.resolve()

        try:
            target.relative_to(root)
        except ValueError:
            return ToolResult(ok=False, text="", error=f"path outside workspace root: {target}")

        if not target.exists():
            return ToolResult(ok=False, text="", error=f"file not found: {target}")

        if not target.is_file():
            return ToolResult(ok=False, text="", error=f"not a file: {target}")

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return ToolResult(ok=False, text="", error=f"read error: {e}")

        lines = content.splitlines()
        total_lines = len(lines)

        start = max(1, int(start_line) if start_line is not None else 1)
        end = min(total_lines, int(end_line) if end_line is not None else total_lines)
        if end < start:
            end = start

        selected = lines[start - 1 : end]
        text = "\n".join(selected)

        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True

        return ToolResult(
            ok=True,
            text=text,
            data={
                "path": str(target),
                "start_line": start,
                "end_line": end,
                "total_lines": total_lines,
                "truncated": truncated,
            },
        )
